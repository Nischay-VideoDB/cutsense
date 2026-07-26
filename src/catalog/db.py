"""SQLite catalog — source of truth for videos, shots, detections, labels."""

import json
import os
import sqlite3
import threading
from pathlib import Path

# CUTSENSE_DB lets a deploy point the catalog at a mounted volume, so analyses
# submitted by visitors survive a redeploy (a container's own disk does not).
DB_PATH = Path(os.environ.get("CUTSENSE_DB")
               or Path(__file__).resolve().parents[2] / "data" / "cutsense.sqlite")

# Detection runs classify shots across a thread pool, so the connection is shared
# across threads and every statement goes through this lock.
LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY,
  videodb_id TEXT UNIQUE NOT NULL,
  title TEXT, source_url TEXT, creator TEXT, technique_hint TEXT,
  duration_s REAL, uploaded_at TEXT DEFAULT (datetime('now')),
  -- which VideoDB account holds this asset; 'legacy' rows predate the project account
  account TEXT DEFAULT 'primary',
  content_index_id TEXT
);
CREATE TABLE IF NOT EXISTS shots (
  id INTEGER PRIMARY KEY,
  videodb_id TEXT NOT NULL,
  scene_collection_id TEXT, idx INTEGER, start_s REAL, end_s REAL,
  UNIQUE(videodb_id, scene_collection_id, idx)
);
CREATE TABLE IF NOT EXISTS detections (
  id INTEGER PRIMARY KEY,
  videodb_id TEXT NOT NULL,
  shot_idx INTEGER, technique TEXT, confidence REAL,
  window_start_s REAL, window_end_s REAL, cut_time_s REAL,
  evidence TEXT, prompt_version TEXT, raw_json TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS analyses (  -- "paste your video" jobs
  id INTEGER PRIMARY KEY,
  source_url TEXT, videodb_id TEXT, title TEXT,
  state TEXT DEFAULT 'queued',   -- queued|uploading|extracting|detecting|ready|failed
  stage_detail TEXT, shots INTEGER, detections INTEGER, error TEXT,
  created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS clip_assets (  -- playable assets per detection; HLS urls expire
  detection_id INTEGER PRIMARY KEY,
  stream_url TEXT, thumbnail_url TEXT, refreshed_at TEXT
);
CREATE TABLE IF NOT EXISTS reels (
  id INTEGER PRIMARY KEY,
  name TEXT, query TEXT, clip_order_json TEXT,
  stream_url TEXT, mp4_url TEXT, created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS frame_descs (  -- cache: VLM frame descriptions are reusable
  frame_id TEXT PRIMARY KEY,
  videodb_id TEXT, frame_time REAL, prompt_tag TEXT, description TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS labels (  -- hand-labeled ground truth for eval
  id INTEGER PRIMARY KEY,
  videodb_id TEXT NOT NULL,
  technique TEXT NOT NULL,
  cut_time_s REAL NOT NULL,   -- approximate time of the cut/technique
  note TEXT,
  UNIQUE(videodb_id, technique, cut_time_s)
);
"""


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    _migrate(db)
    return db


def _migrate(db):
    """Add columns introduced after the first rows were written."""
    have = {r["name"] for r in db.execute("PRAGMA table_info(videos)")}
    for col, ddl in (("account", "TEXT DEFAULT 'primary'"), ("content_index_id", "TEXT")):
        if col not in have:
            db.execute(f"ALTER TABLE videos ADD COLUMN {col} {ddl}")
    db.commit()


def upsert_video(db, videodb_id, **fields):
    cols = ", ".join(fields)
    with LOCK:
        db.execute(
            f"INSERT INTO videos (videodb_id, {cols}) VALUES (?, {','.join('?' * len(fields))}) "
            f"ON CONFLICT(videodb_id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in fields),
            [videodb_id, *fields.values()],
        )
        db.commit()


def get_frame_desc(db, frame_id, prompt_tag):
    with LOCK:
        row = db.execute("SELECT description FROM frame_descs WHERE frame_id=? AND prompt_tag=?",
                         [frame_id, prompt_tag]).fetchone()
    return row["description"] if row else None


def put_frame_desc(db, frame_id, videodb_id, frame_time, prompt_tag, description):
    with LOCK:
        db.execute(
            "INSERT OR REPLACE INTO frame_descs (frame_id, videodb_id, frame_time, prompt_tag, description)"
            " VALUES (?,?,?,?,?)", [frame_id, videodb_id, frame_time, prompt_tag, description])
        db.commit()


def add_detection(db, videodb_id, shot_idx, result: dict, window, cut_time, prompt_version):
    with LOCK:
        db.execute(
            "INSERT INTO detections (videodb_id, shot_idx, technique, confidence, window_start_s,"
            " window_end_s, cut_time_s, evidence, prompt_version, raw_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            [videodb_id, shot_idx, result.get("label"), result.get("confidence"),
             window[0], window[1], cut_time, result.get("evidence"), prompt_version,
             json.dumps(result)],
        )
        db.commit()
