"""Study reels: stitch every instance of a technique into one playable compilation.

Cross-video stitching is native to VideoDB — a timeline of (video, start, end)
assets compiles to a single HLS stream with no local ffmpeg and no render wait.
The newer editor API is tried first for its title/transition support, with the
proven legacy timeline as the fallback so a reel is always produced.
"""

import json

from src.catalog.db import LOCK
from src.videodb_client import get_conn

MAX_CLIPS = 24          # a study reel is a lesson, not a dump
DEFAULT_CLIP_PAD = 0.0  # detection windows already carry ~1.5s either side of the cut


def _segments(clips, limit=MAX_CLIPS):
    out = []
    for c in clips[:limit]:
        start = max(0.0, float(c["window_start_s"]) - DEFAULT_CLIP_PAD)
        end = float(c["window_end_s"]) + DEFAULT_CLIP_PAD
        if end > start:
            out.append({"video_id": c["videodb_id"], "start": round(start, 3),
                        "end": round(end, 3), "clip_id": c["id"],
                        "technique": c["technique"], "title": c["title"]})
    return out


def _compile_editor(conn, segments):
    from videodb.editor import Timeline, Track, VideoAsset
    from videodb.editor import Clip as EditorClip

    timeline = Timeline(conn)
    track = Track(z_index=0)
    cursor = 0.0
    for seg in segments:
        duration = round(seg["end"] - seg["start"], 3)
        track.add_clip(cursor, EditorClip(
            asset=VideoAsset(id=seg["video_id"], start=seg["start"]), duration=duration))
        cursor += duration
    timeline.add_track(track)
    return timeline.generate_stream()


def _compile_legacy(conn, segments):
    from videodb.asset import VideoAsset
    from videodb.timeline import Timeline

    timeline = Timeline(conn)
    for seg in segments:
        timeline.add_inline(VideoAsset(asset_id=seg["video_id"], start=seg["start"],
                                       end=seg["end"]))
    return timeline.generate_stream()


def build_reel(db, clips, name, query=None, account="primary", limit=MAX_CLIPS):
    """Compile clips into one stream. Returns the reel record, or None if nothing to stitch."""
    segments = _segments(clips, limit)
    if not segments:
        return None

    conn = get_conn(account)
    note = None
    try:
        stream_url = _compile_editor(conn, segments)
    except Exception as e:
        stream_url = _compile_legacy(conn, segments)
        note = f"built with the legacy timeline ({type(e).__name__})"

    total = round(sum(s["end"] - s["start"] for s in segments), 2)
    with LOCK:
        cur = db.execute(
            "INSERT INTO reels (name, query, clip_order_json, stream_url) VALUES (?,?,?,?)",
            [name, query, json.dumps(segments), stream_url])
        db.commit()
        reel_id = cur.lastrowid

    return {"id": reel_id, "name": name, "query": query, "stream_url": stream_url,
            "clips": len(segments), "duration_s": total, "segments": segments, "note": note}


def export_mp4(db, reel_id, account="primary"):
    """Turn a reel's stream into a downloadable MP4 (billed per minute)."""
    with LOCK:
        row = db.execute("SELECT * FROM reels WHERE id=?", [reel_id]).fetchone()
    if not row:
        return None
    if row["mp4_url"]:
        return {"id": reel_id, "mp4_url": row["mp4_url"], "cached": True}

    conn = get_conn(account)
    result = conn.download(row["stream_url"], f"cutsense-reel-{reel_id}.mp4")
    url = result.get("download_url") if isinstance(result, dict) else None
    if url:
        with LOCK:
            db.execute("UPDATE reels SET mp4_url=? WHERE id=?", [url, reel_id])
            db.commit()
    return {"id": reel_id, "mp4_url": url, "status": (result or {}).get("status"), "cached": False}
