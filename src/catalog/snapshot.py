"""Catalog snapshot: a git-tracked JSON export of everything the UI needs.

Railway (and any container host) gives us an ephemeral filesystem, so the SQLite
catalog does not survive a redeploy. The snapshot ships inside the image and
seeds an empty database on boot, so a fresh deploy comes up with a warm library.
Detections are cheap to re-derive locally but expensive in API calls — never
depend on the container to hold them.
"""

import json
from pathlib import Path

from src.catalog.db import LOCK

SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "library" / "catalog-snapshot.json"

TABLES = {
    "videos": ["videodb_id", "title", "source_url", "creator", "technique_hint",
               "duration_s", "account", "content_index_id"],
    "detections": ["videodb_id", "shot_idx", "technique", "confidence", "window_start_s",
                   "window_end_s", "cut_time_s", "evidence", "prompt_version", "raw_json",
                   "verified", "verify_note"],
}


def export_snapshot(db, path=SNAPSHOT_PATH):
    """Write accepted detections, their videos, and cached thumbnails to the snapshot."""
    payload = {"videos": [], "detections": [], "thumbnails": []}
    payload["videos"] = [dict(r) for r in db.execute(
        f"SELECT {', '.join(TABLES['videos'])} FROM videos")]
    payload["detections"] = [dict(r) for r in db.execute(
        f"SELECT {', '.join(TABLES['detections'])} FROM detections"
        " WHERE technique NOT LIKE 'rejected:%' AND technique NOT IN ('hard_cut','unclear')")]
    # Thumbnails are stable URLs but clip_assets keys on detection id, which is
    # reassigned on seed — so carry the natural key instead and remap on the way in.
    # Without this a fresh container regenerates every thumbnail through the API.
    payload["thumbnails"] = [dict(r) for r in db.execute(
        "SELECT d.videodb_id, d.cut_time_s, d.technique, a.thumbnail_url"
        " FROM clip_assets a JOIN detections d ON d.id = a.detection_id"
        " WHERE a.thumbnail_url IS NOT NULL"
        " AND d.technique NOT LIKE 'rejected:%' AND d.technique NOT IN ('hard_cut','unclear')")]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1))
    return {k: len(v) for k, v in payload.items()}


def seed_if_empty(db, path=SNAPSHOT_PATH):
    """Load the snapshot when the database has no detections yet."""
    with LOCK:
        have = db.execute("SELECT COUNT(*) c FROM detections").fetchone()["c"]
    if have or not path.exists():
        return {"seeded": False, "detections": have}

    payload = json.loads(path.read_text())
    with LOCK:
        for table, cols in TABLES.items():
            rows = payload.get(table, [])
            if not rows:
                continue
            placeholders = ",".join("?" * len(cols))
            db.executemany(
                f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                [[r.get(c) for c in cols] for r in rows])

        ids = {(r["videodb_id"], round(r["cut_time_s"], 3), r["technique"]): r["id"]
               for r in db.execute("SELECT id, videodb_id, cut_time_s, technique FROM detections")}
        thumbs = []
        for t in payload.get("thumbnails", []):
            key = (t["videodb_id"], round(t["cut_time_s"], 3), t["technique"])
            if key in ids:
                thumbs.append([ids[key], t["thumbnail_url"]])
        db.executemany(
            "INSERT OR IGNORE INTO clip_assets (detection_id, thumbnail_url) VALUES (?,?)", thumbs)
        db.commit()
    return {"seeded": True, "thumbnails_mapped": len(thumbs),
            **{k: len(v) for k, v in payload.items()}}
