"""Style profiles: a creator's or video's editing signature, with evidence clips.

Structured JSON by design — the brief calls for other tools and agents to be able
to consume the archive, so every number here is machine-readable and the prose
summary is one field among many, not the payload.
"""

import json
import re

from src.detect.prompts import SHIPPING_TECHNIQUES, TECHNIQUE_LABELS
from src.profiles import pacing

SIGNATURE_PROMPT = """You are describing a video editor's cutting signature from measured data.

Creator: {name}
Videos: {videos}
Cuts per minute: {cpm}
Average cut length: {avg}s (median {median}s)
Share of cuts under 1.2s: {fast}
Rhythmic cutting detected: {rhythmic}
Technique counts: {techniques}

Write 2-3 sentences an editor would find useful: how this work is cut, what it
reaches for, and what the pacing feels like. Reference the numbers rather than
repeating them all. No preamble, no bullet points, no hedging."""

# "Nike - Nothing Beats a Londoner", "ONHA - KODAK (Clip...)", "USHER, H.E.R. - Risk It All"
CREATOR_SPLIT = re.compile(r"\s+[-–—]\s+|\s+\|\s+")


def creator_from_title(title):
    if not title:
        return None
    head = CREATOR_SPLIT.split(title)[0].strip()
    head = re.sub(r"\s*\(.*?\)\s*", " ", head).strip(" -–—|,")
    if not head or len(head) > 48:
        return None
    return head


def backfill_creators(db):
    """Populate videos.creator from titles where it is unset."""
    rows = db.execute("SELECT videodb_id, title FROM videos WHERE creator IS NULL").fetchall()
    updates = [(creator_from_title(r["title"]), r["videodb_id"]) for r in rows]
    updates = [(c, v) for c, v in updates if c]
    db.executemany("UPDATE videos SET creator=? WHERE videodb_id=?", updates)
    db.commit()
    return len(updates)


def _shots(db, video_ids):
    marks = ",".join("?" * len(video_ids))
    return db.execute(
        f"SELECT videodb_id, start_s, end_s FROM shots WHERE videodb_id IN ({marks})"
        " ORDER BY videodb_id, start_s", video_ids).fetchall()


def _technique_counts(db, video_ids):
    marks = ",".join("?" * len(video_ids))
    tech = ",".join("?" * len(SHIPPING_TECHNIQUES))
    rows = db.execute(
        f"SELECT technique, COUNT(*) n FROM detections WHERE videodb_id IN ({marks})"
        f" AND technique IN ({tech}) AND (verified IS NULL OR verified = 1)"
        " GROUP BY technique",
        [*video_ids, *SHIPPING_TECHNIQUES]).fetchall()
    return {r["technique"]: r["n"] for r in rows}


def _evidence(db, video_ids, limit=6):
    marks = ",".join("?" * len(video_ids))
    tech = ",".join("?" * len(SHIPPING_TECHNIQUES))
    rank = " ".join(f"WHEN ? THEN {i}" for i in range(len(SHIPPING_TECHNIQUES)))
    rows = db.execute(
        f"SELECT d.id, d.technique, d.confidence, d.cut_time_s, d.window_start_s, d.window_end_s,"
        f" v.title FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
        f" WHERE d.videodb_id IN ({marks}) AND d.technique IN ({tech})"
        "   AND (d.verified IS NULL OR d.verified = 1)"
        # rank by technique before confidence: luma fades score 1.00 and are near-black
        # frames, so confidence alone made every evidence thumbnail a black rectangle
        f" ORDER BY CASE d.technique {rank} ELSE 99 END, d.confidence DESC LIMIT ?",
        [*video_ids, *SHIPPING_TECHNIQUES, *SHIPPING_TECHNIQUES, limit]).fetchall()
    return [{"clip_id": r["id"], "technique": r["technique"],
             "technique_label": TECHNIQUE_LABELS.get(r["technique"], r["technique"]),
             "video_title": r["title"], "cut_time_s": r["cut_time_s"],
             "start_s": r["window_start_s"], "end_s": r["window_end_s"],
             "confidence": r["confidence"]} for r in rows]


def build_profile(db, scope, scope_key, coll=None):
    """scope: 'video' | 'creator'. Returns the profile dict, or None if unknown."""
    if scope == "video":
        rows = db.execute("SELECT videodb_id, title FROM videos WHERE videodb_id=?",
                          [scope_key]).fetchall()
        name = rows[0]["title"] if rows else None
    else:
        rows = db.execute("SELECT videodb_id, title FROM videos WHERE creator=?",
                          [scope_key]).fetchall()
        name = scope_key
    if not rows:
        return None

    video_ids = [r["videodb_id"] for r in rows]
    shots = _shots(db, video_ids)

    # per-video pacing, then aggregate across the creator's videos
    per_video = {}
    for vid in video_ids:
        vshots = [s for s in shots if s["videodb_id"] == vid]
        summary = pacing.summarise(vshots)
        if summary:
            per_video[vid] = summary

    counts = _technique_counts(db, video_ids)
    total_cuts = sum(v["cuts"] for v in per_video.values())
    weighted_avg = (sum(v["avg_cut_length_s"] * v["cuts"] for v in per_video.values()) / total_cuts
                    if total_cuts else None)
    rhythmic = [vid for vid, v in per_video.items() if v["rhythm"]["rhythmic"]]

    profile = {
        "scope": scope,
        "key": scope_key,
        "name": name,
        "videos": len(video_ids),
        "video_titles": [r["title"] for r in rows],
        "cuts": total_cuts,
        "avg_cut_length_s": round(weighted_avg, 2) if weighted_avg else None,
        "cuts_per_minute": round(
            sum(v["cuts_per_minute"] or 0 for v in per_video.values()) / len(per_video), 2)
            if per_video else None,
        "fast_cut_share": round(
            sum(v["fast_cut_share"] for v in per_video.values()) / len(per_video), 3)
            if per_video else None,
        "technique_frequency": {TECHNIQUE_LABELS.get(k, k): v
                                for k, v in sorted(counts.items(), key=lambda kv: -kv[1])},
        "techniques_per_minute": None,
        "rhythmic_videos": len(rhythmic),
        "per_video": per_video,
        "evidence_clips": _evidence(db, video_ids),
    }

    minutes = sum(v["duration_s"] for v in per_video.values()) / 60 if per_video else 0
    if minutes:
        profile["techniques_per_minute"] = round(sum(counts.values()) / minutes, 2)

    profile["signature"] = _signature(coll, profile)
    return profile


def _signature(coll, profile):
    """One short prose paragraph. Falls back to a measured description without an LLM."""
    techniques = ", ".join(f"{k} x{v}" for k, v in profile["technique_frequency"].items()) or "none detected"
    if coll is None:
        return (f"{profile['name']}: {profile['cuts']} cuts across {profile['videos']} video(s), "
                f"averaging {profile['avg_cut_length_s']}s per shot "
                f"({profile['cuts_per_minute']} cuts/min). Techniques: {techniques}.")
    prompt = SIGNATURE_PROMPT.format(
        name=profile["name"], videos=profile["videos"],
        cpm=profile["cuts_per_minute"], avg=profile["avg_cut_length_s"],
        median=None, fast=profile["fast_cut_share"],
        rhythmic=f"{profile['rhythmic_videos']} of {profile['videos']} videos",
        techniques=techniques)
    # tiers have separate budgets and one dying is normal, so walk the chain rather
    # than letting a spent tier turn every profile into an error string
    last = None
    for model in ("basic", "pro", "ultra"):
        try:
            raw = coll.generate_text(prompt=prompt, model_name=model)
            text = raw.get("output") if isinstance(raw, dict) else raw
            if text:
                return str(text).strip()
        except Exception as e:
            last = e
            continue
    return f"(signature unavailable: {type(last).__name__ if last else 'no output'})"


def creators(db, min_videos=1):
    rows = db.execute(
        "SELECT v.creator, COUNT(DISTINCT v.videodb_id) videos,"
        " COUNT(d.id) FILTER (WHERE d.technique IN ("
        + ",".join("?" * len(SHIPPING_TECHNIQUES))
        + ") AND (d.verified IS NULL OR d.verified = 1)) detections"
        " FROM videos v LEFT JOIN detections d ON d.videodb_id = v.videodb_id"
        " WHERE v.creator IS NOT NULL GROUP BY v.creator"
        # SQLite accepts a SELECT alias in HAVING; PostgreSQL intentionally does
        # not. Keep the aggregate explicit so the public durable catalog and the
        # local operator catalog execute the same query.
        " HAVING COUNT(DISTINCT v.videodb_id) >= ? ORDER BY detections DESC",
        [*SHIPPING_TECHNIQUES, min_videos]).fetchall()
    return [{"creator": r["creator"], "videos": r["videos"], "detections": r["detections"]}
            for r in rows]
