"""Analyse a video the user pastes: upload → shots → techniques → report.

This is the primary flow. The user brings their own edit (or a reference they
found) and asks what was done to it and how to redo it; the library exists to show
the same technique working elsewhere.

The work takes minutes, so it runs in a background thread with progress in SQLite
and the request returns an id immediately. State lives in the database rather than
in memory so a poll can be served by any worker and survives a reload.
"""

import hashlib
from pathlib import Path

from src.catalog.db import LOCK, add_detection, get_db, upsert_video
from src.detect import pipeline as pl
from src.videodb_client import get_collection

# a long upload plus a long classify pass is fine, but be honest about the ceiling
MAX_DURATION_S = 15 * 60


def create(db, source_url):
    key = hashlib.sha256(source_url.encode()).hexdigest()
    with LOCK:
        cur = db.execute(
            "INSERT INTO analyses (source_url, state, idempotency_key) "
            "VALUES (?, 'queued', ?) ON CONFLICT (idempotency_key) DO NOTHING "
            "RETURNING id",
            [source_url, key],
        )
        row = db.execute(
            "SELECT id FROM analyses WHERE idempotency_key=?", [key]
        ).fetchone()
        analysis_id = row["id"]
        db.commit()
        return analysis_id


def update(db, analysis_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with LOCK:
        db.execute(f"UPDATE analyses SET {sets}, updated_at=datetime('now') WHERE id=?",
                   [*fields.values(), analysis_id])
        db.commit()


def get(db, analysis_id):
    with LOCK:
        row = db.execute("SELECT * FROM analyses WHERE id=?", [analysis_id]).fetchone()
    return dict(row) if row else None


def find_by_url(db, source_url):
    """Reuse a finished analysis of the same URL instead of paying for it twice."""
    with LOCK:
        row = db.execute(
            "SELECT * FROM analyses WHERE source_url=? AND state='ready' ORDER BY id DESC LIMIT 1",
            [source_url]).fetchone()
    return dict(row) if row else None


def run(analysis_id, source_url, file_path=None):
    """Worker body. Owns its own connection: SQLite objects are per-thread.

    `file_path` handles uploads: the same pipeline, sourced from disk instead of a URL.
    """
    db = get_db()
    try:
        coll = get_collection()
        # uploading the same URL twice creates a second asset (billed, stored), so
        # reuse a copy we already hold
        with LOCK:
            known = db.execute(
                "SELECT v.videodb_id, v.title, v.duration_s FROM videos v"
                " WHERE v.source_url=? AND v.account='primary'"
                " AND EXISTS (SELECT 1 FROM shots s WHERE s.videodb_id = v.videodb_id)"
                " ORDER BY v.rowid DESC LIMIT 1", [source_url]).fetchone()
        if known and not file_path:
            update(db, analysis_id, state="extracting", videodb_id=known["videodb_id"],
                   title=known["title"], stage_detail="already in the archive — re-reading it")
            video = coll.get_video(known["videodb_id"])
        elif file_path:
            update(db, analysis_id, state="uploading", stage_detail="uploading your file")
            video = coll.upload(file_path=file_path)
        else:
            update(db, analysis_id, state="uploading", stage_detail="fetching the video")
            video = coll.upload(url=source_url)
        length = float(getattr(video, "length", 0) or 0)
        title = getattr(video, "name", None)
        update(db, analysis_id, videodb_id=video.id, title=title,
               stage_detail=f"{title or 'video'} · {length:.0f}s")

        if length > MAX_DURATION_S:
            update(db, analysis_id, state="failed",
                   error=f"video is {length / 60:.1f} min; the limit is {MAX_DURATION_S // 60} min")
            return

        upsert_video(db, video.id, title=title, source_url=source_url, duration_s=length,
                     account="primary")

        update(db, analysis_id, state="extracting", stage_detail="finding the cuts")
        sc = pl.extract_shots(video)
        scenes = sc.scenes
        with LOCK:
            db.executemany(
                "INSERT OR IGNORE INTO shots (videodb_id, scene_collection_id, idx, start_s, end_s)"
                " VALUES (?,?,?,?,?)",
                [(video.id, sc.id, i, s.start, s.end) for i, s in enumerate(scenes)])
            db.commit()
        update(db, analysis_id, shots=len(scenes), state="detecting",
               stage_detail=f"reading {len(scenes)} cuts")

        results = pl.classify_shots_parallel(sc)
        update(db, analysis_id,
               stage_detail=f"reading {len(scenes)} cuts (model: {pl.model_for() or 'default'})")
        kept = 0
        errors = 0
        for i, scene, result in results:
            window = pl.detection_window(scene, length or scene.end)
            ok, reason = pl.validate_detection(scene, result)
            label = result.get("label") if ok else f"rejected:{result.get('label')}"
            # keep the model's own words; the rejection reason is prefixed, never a
            # replacement — overwriting it once hid a total classifier failure
            evidence = result.get("evidence")
            if not ok:
                evidence = f"[{reason}] {evidence or ''}".strip()
            add_detection(db, video.id, i, {**result, "label": label, "evidence": evidence},
                          window, scene.start, pl.PROMPT_VERSION)
            kept += 1 if ok and label in pl.CONF_THRESHOLD else 0
            errors += 1 if str(result.get("evidence", "")).startswith("error:") else 0

        # a classifier that failed on everything is a failure, not an empty result
        if errors and errors == len(results):
            update(db, analysis_id, state="failed",
                   error=f"the vision model rejected every request: {results[0][2]['evidence'][:160]}")
            return

        detail = f"{kept} techniques found across {len(scenes)} cuts"
        if errors:
            detail += f" ({errors} cuts could not be read)"
        update(db, analysis_id, state="ready", detections=kept, stage_detail=detail)
    except Exception as e:
        update(db, analysis_id, state="failed", error=f"{type(e).__name__}: {e}")
    finally:
        if file_path:
            Path(file_path).unlink(missing_ok=True)   # the asset lives in VideoDB now


def start(db, source_url, file_path=None):
    """Run one durable analysis synchronously on serverless production."""
    if not file_path:
        existing = find_by_url(db, source_url)
        if existing:
            existing["reused"] = True
            return existing
    analysis_id = create(db, source_url)
    current = get(db, analysis_id)
    if current and current["state"] in {"queued", "failed"}:
        run(analysis_id, source_url, file_path)
    return get(db, analysis_id)
