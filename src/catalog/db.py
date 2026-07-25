"""SQLite catalog — source of truth for videos, shots, detections, labels."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cutsense.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY,
  videodb_id TEXT UNIQUE NOT NULL,
  title TEXT, source_url TEXT, creator TEXT, technique_hint TEXT,
  duration_s REAL, uploaded_at TEXT DEFAULT (datetime('now'))
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
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def upsert_video(db, videodb_id, **fields):
    cols = ", ".join(fields)
    db.execute(
        f"INSERT INTO videos (videodb_id, {cols}) VALUES (?, {','.join('?' * len(fields))}) "
        f"ON CONFLICT(videodb_id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in fields),
        [videodb_id, *fields.values()],
    )
    db.commit()


def add_detection(db, videodb_id, shot_idx, result: dict, window, cut_time, prompt_version):
    db.execute(
        "INSERT INTO detections (videodb_id, shot_idx, technique, confidence, window_start_s,"
        " window_end_s, cut_time_s, evidence, prompt_version, raw_json)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        [videodb_id, shot_idx, result.get("label"), result.get("confidence"),
         window[0], window[1], cut_time, result.get("evidence"), prompt_version,
         json.dumps(result)],
    )
    db.commit()
