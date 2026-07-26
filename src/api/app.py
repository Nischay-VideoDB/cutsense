"""CutSense HTTP API + static UI.

Run locally:  .venv/bin/uvicorn src.api.app:app --reload --port 8000
"""

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api import clips as clip_service
from src.catalog.db import get_db
from src.catalog.snapshot import seed_if_empty
from src.detect.prompts import SHIPPING_TECHNIQUES, TECHNIQUE_LABELS
from src.videodb_client import NotConfigured

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
RECIPE_DIR = ROOT / "docs" / "recipes"
VERSION = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "dev")[:9]

app = FastAPI(title="CutSense", description="Searchable technique archive for editors")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = get_db()
SEED = seed_if_empty(db)   # a container starts with an empty disk; ship a warm library


def technique_filter_sql(alias="d"):
    """Only the vocabulary we ship — excludes hard_cut, unclear and rejected rows."""
    return f"{alias}.technique IN ({','.join('?' * len(SHIPPING_TECHNIQUES))})"


# Several videos were ingested into both accounts, which would show the same moment
# twice. Prefer the project account and hide the legacy twin.
NOT_DUPLICATE_SQL = """NOT (v.account = 'legacy' AND EXISTS (
  SELECT 1 FROM videos p WHERE p.account = 'primary'
    AND (p.title = v.title OR (v.source_url IS NOT NULL AND p.source_url = v.source_url))))"""


def detection_row(row, with_assets=False, want_stream=True):
    payload = {
        "id": row["id"],
        "technique": row["technique"],
        "technique_label": TECHNIQUE_LABELS.get(row["technique"], row["technique"]),
        "confidence": row["confidence"],
        "video_id": row["videodb_id"],
        "video_title": row["title"],
        "source_url": row["source_url"],
        "creator": row["creator"],
        "cut_time_s": row["cut_time_s"],
        "start_s": row["window_start_s"],
        "end_s": row["window_end_s"],
        "evidence": row["evidence"],
    }
    if with_assets:
        try:
            payload.update(clip_service.clip_assets(
                db, row, account=row["account"] or "primary", want_stream=want_stream))
        except Exception as e:
            payload["asset_error"] = str(e)
    return payload


@app.get("/api/health")
def health():
    counts = {r["technique"]: r["n"] for r in db.execute(
        "SELECT d.technique, COUNT(*) n FROM detections d"
        " JOIN videos v ON v.videodb_id = d.videodb_id"
        f" WHERE {technique_filter_sql()} AND {NOT_DUPLICATE_SQL}"
        " GROUP BY d.technique", SHIPPING_TECHNIQUES)}
    return {"ok": True, "version": VERSION, "seed": SEED,
            "videos": db.execute(
                "SELECT COUNT(DISTINCT d.videodb_id) c FROM detections d"
                " JOIN videos v ON v.videodb_id = d.videodb_id"
                f" WHERE {technique_filter_sql()} AND {NOT_DUPLICATE_SQL}",
                SHIPPING_TECHNIQUES).fetchone()["c"],
            "videos_total": db.execute(
                f"SELECT COUNT(*) c FROM videos v WHERE {NOT_DUPLICATE_SQL}").fetchone()["c"],
            "detections": counts}


@app.get("/api/techniques")
def techniques():
    counts = {r["technique"]: r["n"] for r in db.execute(
        "SELECT d.technique, COUNT(*) n FROM detections d"
        " JOIN videos v ON v.videodb_id = d.videodb_id"
        f" WHERE {NOT_DUPLICATE_SQL} GROUP BY d.technique")}
    return [{"id": t, "label": TECHNIQUE_LABELS[t], "count": counts.get(t, 0)}
            for t in SHIPPING_TECHNIQUES]


@app.get("/api/clips")
def list_clips(technique: str | None = None, q: str | None = None,
               video_id: str | None = None, limit: int = Query(24, le=200),
               offset: int = 0, assets: bool = True):
    where, params = [technique_filter_sql(), NOT_DUPLICATE_SQL], list(SHIPPING_TECHNIQUES)
    if technique:
        where.append("d.technique = ?")
        params.append(technique)
    if video_id:
        where.append("d.videodb_id = ?")
        params.append(video_id)
    if q:
        where.append("(v.title LIKE ? OR d.evidence LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    # SHIPPING_TECHNIQUES order is also the display order: luma fades are near-black
    # frames, so leading with them makes the grid look empty. Within a technique,
    # rank by confidence.
    rank = " ".join(f"WHEN ? THEN {i}" for i in range(len(SHIPPING_TECHNIQUES)))
    rows = db.execute(
        "SELECT d.*, v.title, v.source_url, v.creator, v.account FROM detections d"
        " JOIN videos v ON v.videodb_id = d.videodb_id"
        f" WHERE {' AND '.join(where)}"
        f" ORDER BY CASE d.technique {rank} ELSE 99 END, d.confidence DESC, d.id"
        " LIMIT ? OFFSET ?",
        [*params, *SHIPPING_TECHNIQUES, limit, offset]).fetchall()

    if not assets:
        return {"count": len(rows), "clips": [detection_row(r) for r in rows]}

    # each uncached clip costs a VideoDB round trip; fan them out so first paint
    # is one round trip deep instead of `limit` deep
    with ThreadPoolExecutor(max_workers=8) as pool:
        clips = list(pool.map(
            lambda r: detection_row(r, with_assets=True, want_stream=False), rows))
    return {"count": len(clips), "clips": clips}


@app.get("/api/thumb/{detection_id}")
def thumb(detection_id: int):
    """Serve the grid thumbnail from our own origin.

    Keeps the page single-origin (no third-party image host to be blocked or to
    leak referrers), lets the browser cache aggressively, and hides VideoDB URLs.
    """
    row = db.execute(
        "SELECT d.*, v.account FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
        " WHERE d.id = ?", [detection_id]).fetchone()
    if not row:
        raise HTTPException(404, "clip not found")
    try:
        url = clip_service.clip_assets(
            db, row, account=row["account"] or "primary", want_stream=False)["thumbnail_url"]
    except NotConfigured as e:
        raise HTTPException(503, f"thumbnail unavailable: {e}")
    if not url:
        raise HTTPException(404, "no thumbnail")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body, content_type = r.read(), r.headers.get("content-type", "image/png")
    except Exception as e:
        raise HTTPException(502, f"thumbnail fetch failed: {e}")
    return Response(content=body, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/clips/{detection_id}/stream")
def clip_stream(detection_id: int):
    """Playable URL on demand — the grid only needs thumbnails until you hover."""
    row = db.execute(
        "SELECT d.*, v.account FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
        " WHERE d.id = ?", [detection_id]).fetchone()
    if not row:
        raise HTTPException(404, "clip not found")
    try:
        return clip_service.clip_assets(db, row, account=row["account"] or "primary")
    except NotConfigured as e:
        # streams are generated on demand, so this is the one path that needs a key
        raise HTTPException(503, f"playback unavailable: {e}")


@app.get("/api/clips/{detection_id}")
def get_clip(detection_id: int):
    row = db.execute(
        "SELECT d.*, v.title, v.source_url, v.creator, v.account FROM detections d"
        " JOIN videos v ON v.videodb_id = d.videodb_id WHERE d.id = ?", [detection_id]).fetchone()
    if not row:
        raise HTTPException(404, "clip not found")
    payload = detection_row(row, with_assets=True)
    payload["recipe"] = read_recipe(row["technique"])
    payload["judge"] = json.loads(row["raw_json"] or "{}")
    return payload


def read_recipe(technique):
    path = RECIPE_DIR / f"{technique.replace('_', '-')}.md"
    return path.read_text() if path.exists() else None


@app.get("/api/recipes/{technique}")
def recipe(technique: str):
    body = read_recipe(technique)
    if body is None:
        raise HTTPException(404, f"no recipe for {technique}")
    return {"technique": technique, "label": TECHNIQUE_LABELS.get(technique, technique),
            "markdown": body}


@app.get("/api/videos")
def videos():
    rows = db.execute(
        f"SELECT v.*, COUNT(d.id) FILTER (WHERE {technique_filter_sql()}) AS detections"
        " FROM videos v LEFT JOIN detections d ON d.videodb_id = v.videodb_id"
        f" WHERE {NOT_DUPLICATE_SQL}"
        " GROUP BY v.videodb_id ORDER BY detections DESC", SHIPPING_TECHNIQUES).fetchall()
    return [{"video_id": r["videodb_id"], "title": r["title"], "source_url": r["source_url"],
             "duration_s": r["duration_s"], "technique_hint": r["technique_hint"],
             "detections": r["detections"], "account": r["account"]} for r in rows]


def asset_version():
    """Cache-busting token: newest mtime of the static assets, or the commit sha.

    Without this the browser happily serves a stale app.js after a deploy (or an
    edit), which looks exactly like a broken feature.
    """
    if VERSION != "dev":
        return VERSION
    try:
        return str(int(max((WEB_DIR / f).stat().st_mtime for f in ("app.js", "styles.css"))))
    except OSError:
        return "dev"


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index():
        html = (WEB_DIR / "index.html").read_text().replace("__ASSET_V__", asset_version())
        return Response(content=html, media_type="text/html",
                        headers={"Cache-Control": "no-store"})
