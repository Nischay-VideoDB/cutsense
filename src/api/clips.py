"""Clip assets: playable HLS windows and grid thumbnails for detections.

VideoDB stream URLs expire in roughly 24h, so they are cached with a refresh
timestamp and regenerated on demand rather than treated as durable.
"""

from datetime import datetime, timedelta, timezone

from src.catalog.db import LOCK
from src.videodb_client import get_collection

STREAM_TTL = timedelta(hours=18)   # comfortably inside VideoDB's ~24h expiry
_video_cache = {}


def _now():
    return datetime.now(timezone.utc)


def _fresh(refreshed_at):
    if not refreshed_at:
        return False
    try:
        return _now() - datetime.fromisoformat(refreshed_at) < STREAM_TTL
    except ValueError:
        return False


def _video(videodb_id, account="primary"):
    key = (account, videodb_id)
    if key not in _video_cache:
        _video_cache[key] = get_collection(account=account).get_video(videodb_id)
    return _video_cache[key]


def _make_thumbnail(video, cut_time, offsets=(0.0, 0.4, -0.4)):
    """Generate a poster near the cut, tolerating timestamps the encoder refuses.

    Some timestamps simply fail (a cut landing on the last frame, for one), so a
    single attempt at the exact cut leaves a hole in the grid.
    """
    duration = float(getattr(video, "length", 0) or 0)
    for off in offsets:
        t = cut_time + off
        if t < 0 or (duration and t > duration - 0.05):
            continue
        try:
            thumb = video.generate_thumbnail(time=float(t))
            url = getattr(thumb, "url", thumb)
            if url:
                return url
        except Exception:
            continue
    return None


def clip_assets(db, detection, account="primary", want_thumbnail=True, want_stream=True):
    """Return {stream_url, thumbnail_url} for a detection row, refreshing if stale.

    The grid asks for thumbnails only (`want_stream=False`) — generating a stream per
    card doubles the cold cost for something you only need once the pointer lands.
    Thumbnails are stable storage URLs; only streams expire.
    """
    with LOCK:
        row = db.execute("SELECT * FROM clip_assets WHERE detection_id=?",
                         [detection["id"]]).fetchone()
    have_stream = bool(row and row["stream_url"] and _fresh(row["refreshed_at"]))
    have_thumb = bool(row and row["thumbnail_url"])
    if (have_stream or not want_stream) and (have_thumb or not want_thumbnail):
        return {"stream_url": row["stream_url"] if have_stream else None,
                "thumbnail_url": row["thumbnail_url"] if row else None}

    video = _video(detection["videodb_id"], account)
    stream_url = row["stream_url"] if have_stream else None
    if want_stream and not stream_url:
        start = max(0.0, float(detection["window_start_s"]))
        end = float(detection["window_end_s"])
        stream_url = video.generate_stream(timeline=[(start, end)])

    thumbnail_url = row["thumbnail_url"] if row else None
    if want_thumbnail and not thumbnail_url:
        thumbnail_url = _make_thumbnail(video, float(detection["cut_time_s"]))

    with LOCK:
        db.execute(
            "INSERT OR REPLACE INTO clip_assets (detection_id, stream_url, thumbnail_url,"
            " refreshed_at) VALUES (?,?,?,?)",
            [detection["id"], stream_url, thumbnail_url,
             _now().isoformat() if stream_url else (row["refreshed_at"] if row else None)])
        db.commit()
    return {"stream_url": stream_url, "thumbnail_url": thumbnail_url}
