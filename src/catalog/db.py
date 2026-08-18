"""SQLite catalog — source of truth for videos, shots, detections, labels."""

import json
import os
import sqlite3
import threading
import re
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
  idempotency_key TEXT UNIQUE,
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
  name TEXT, query TEXT, clip_order_json TEXT, idempotency_key TEXT UNIQUE,
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

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id BIGSERIAL PRIMARY KEY,
  videodb_id TEXT UNIQUE NOT NULL,
  title TEXT, source_url TEXT, creator TEXT, technique_hint TEXT,
  duration_s DOUBLE PRECISION, uploaded_at TIMESTAMPTZ DEFAULT now(),
  account TEXT DEFAULT 'primary', content_index_id TEXT
);
CREATE TABLE IF NOT EXISTS shots (
  id BIGSERIAL PRIMARY KEY,
  videodb_id TEXT NOT NULL, scene_collection_id TEXT, idx INTEGER,
  start_s DOUBLE PRECISION, end_s DOUBLE PRECISION,
  UNIQUE(videodb_id, scene_collection_id, idx)
);
CREATE TABLE IF NOT EXISTS detections (
  id BIGSERIAL PRIMARY KEY,
  videodb_id TEXT NOT NULL, shot_idx INTEGER, technique TEXT,
  confidence DOUBLE PRECISION, window_start_s DOUBLE PRECISION,
  window_end_s DOUBLE PRECISION, cut_time_s DOUBLE PRECISION,
  evidence TEXT, prompt_version TEXT, raw_json TEXT,
  created_at TIMESTAMPTZ DEFAULT now(), verified INTEGER, verify_note TEXT,
  UNIQUE(videodb_id, shot_idx, technique, cut_time_s)
);
CREATE TABLE IF NOT EXISTS analyses (
  id BIGSERIAL PRIMARY KEY, source_url TEXT, videodb_id TEXT, title TEXT,
  state TEXT DEFAULT 'queued', stage_detail TEXT, shots INTEGER,
  detections INTEGER, error TEXT, idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS clip_assets (
  detection_id BIGINT PRIMARY KEY REFERENCES detections(id) ON DELETE CASCADE,
  stream_url TEXT, thumbnail_url TEXT, refreshed_at TEXT
);
CREATE TABLE IF NOT EXISTS reels (
  id BIGSERIAL PRIMARY KEY, name TEXT, query TEXT, clip_order_json TEXT,
  stream_url TEXT, mp4_url TEXT, idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE reels ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_reels_idempotency ON reels(idempotency_key);
CREATE TABLE IF NOT EXISTS frame_descs (
  frame_id TEXT PRIMARY KEY, videodb_id TEXT, frame_time DOUBLE PRECISION,
  prompt_tag TEXT, description TEXT, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS labels (
  id BIGSERIAL PRIMARY KEY, videodb_id TEXT NOT NULL, technique TEXT NOT NULL,
  cut_time_s DOUBLE PRECISION NOT NULL, note TEXT,
  UNIQUE(videodb_id, technique, cut_time_s)
);
CREATE TABLE IF NOT EXISTS analysis_rate (
  actor_hash TEXT NOT NULL, bucket TIMESTAMPTZ NOT NULL,
  requests INTEGER NOT NULL, PRIMARY KEY(actor_hash, bucket)
);
"""


class _Result:
    def __init__(self, rows=None, lastrowid=None):
        self._rows = rows or []
        self._at = 0
        self.lastrowid = lastrowid

    def fetchone(self):
        if self._at >= len(self._rows):
            return None
        row = self._rows[self._at]
        self._at += 1
        return row

    def fetchall(self):
        rows = self._rows[self._at:]
        self._at = len(self._rows)
        return rows

    def __iter__(self):
        return iter(self._rows)


class PostgresDB:
    """Small DB-API compatibility layer over a bounded psycopg connection pool.

    Existing query code keeps its SQLite-style placeholders, while production
    stores every mutable record in Azure Postgres.  Connections are autocommit
    and returned after each statement, which is safe for serverless reuse.
    """

    def __init__(self, url):
        from psycopg_pool import ConnectionPool
        self.pool = ConnectionPool(
            conninfo=url.replace("sslmode=no-verify", "sslmode=require"),
            min_size=0,
            max_size=int(os.getenv("CUTSENSE_DB_POOL_SIZE", "4")),
            kwargs={"autocommit": True, "row_factory": __import__(
                "psycopg.rows", fromlist=["dict_row"]
            ).dict_row},
        )
        with self.pool.connection() as conn:
            for statement in POSTGRES_SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)

    @staticmethod
    def _sql(sql):
        sql = sql.replace("datetime('now')", "now()").replace("v.rowid", "v.id")
        ignore = bool(re.match(r"\s*INSERT OR IGNORE", sql, re.I))
        sql = re.sub(r"INSERT OR IGNORE", "INSERT", sql, flags=re.I)
        if re.match(r"\s*INSERT OR REPLACE INTO clip_assets", sql, re.I):
            sql = re.sub(r"INSERT OR REPLACE", "INSERT", sql, flags=re.I)
            sql += (
                " ON CONFLICT (detection_id) DO UPDATE SET "
                "stream_url=EXCLUDED.stream_url, thumbnail_url=EXCLUDED.thumbnail_url, "
                "refreshed_at=EXCLUDED.refreshed_at"
            )
        elif re.match(r"\s*INSERT OR REPLACE INTO frame_descs", sql, re.I):
            sql = re.sub(r"INSERT OR REPLACE", "INSERT", sql, flags=re.I)
            sql += (
                " ON CONFLICT (frame_id) DO UPDATE SET videodb_id=EXCLUDED.videodb_id, "
                "frame_time=EXCLUDED.frame_time, prompt_tag=EXCLUDED.prompt_tag, "
                "description=EXCLUDED.description"
            )
        elif ignore:
            sql += " ON CONFLICT DO NOTHING"
        sql = sql.replace("?", "%s")
        wants_id = bool(re.match(r"\s*INSERT INTO (analyses|reels)\b", sql, re.I))
        if wants_id and " RETURNING " not in sql.upper():
            sql += " RETURNING id"
        return sql, wants_id

    def execute(self, sql, params=None):
        translated, wants_id = self._sql(sql)
        with self.pool.connection() as conn:
            cur = conn.execute(translated, params or [])
            rows = cur.fetchall() if cur.description else []
        lastrowid = rows[0]["id"] if wants_id and rows else None
        return _Result(rows, lastrowid)

    def executemany(self, sql, params):
        translated, _ = self._sql(sql)
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(translated, params)
        return _Result()

    def commit(self):
        return None

    def rollback(self):
        return None


def get_db():
    database_url = os.environ.get("CUTSENSE_DATABASE_URL")
    if database_url:
        return PostgresDB(database_url)
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
    # An independent second-opinion audit refuted most detections, so a detection is
    # not trustworthy until something other than the original classifier agrees.
    # NULL = not yet audited, 1 = confirmed, 0 = refuted.
    det = {r["name"] for r in db.execute("PRAGMA table_info(detections)")}
    for col, ddl in (("verified", "INTEGER"), ("verify_note", "TEXT")):
        if col not in det:
            db.execute(f"ALTER TABLE detections ADD COLUMN {col} {ddl}")
    analyses = {r["name"] for r in db.execute("PRAGMA table_info(analyses)")}
    if "idempotency_key" not in analyses:
        db.execute("ALTER TABLE analyses ADD COLUMN idempotency_key TEXT")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analyses_idempotency "
            "ON analyses(idempotency_key)"
        )
    reels = {r["name"] for r in db.execute("PRAGMA table_info(reels)")}
    if "idempotency_key" not in reels:
        db.execute("ALTER TABLE reels ADD COLUMN idempotency_key TEXT")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_reels_idempotency "
            "ON reels(idempotency_key)"
        )
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
