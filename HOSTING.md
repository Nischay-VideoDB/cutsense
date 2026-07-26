# Hosting CutSense

Target: **Railway** (Docker build, auto-deploy from `main` on `github.com/falgunitripathi`).

## Environment

| Var | Required | Purpose |
|---|---|---|
| `VIDEO_DB_API_KEY` | yes | project VideoDB account (Falgunitripathi8) |
| `VIDEO_DB_API_KEY_LEGACY` | only while legacy assets are served | earlier account holding the first calibration videos |
| `PORT` | injected | Railway sets this; the CMD expands it |
| `RAILWAY_GIT_COMMIT_SHA` | injected | reported by `/api/health` as `version` |

## What survives a redeploy — and what doesn't

The container filesystem is **ephemeral**. `data/cutsense.sqlite` is written at runtime and is gitignored, so a redeploy starts with an empty database.

That is handled deliberately:

- `library/catalog-snapshot.json` is **git-tracked** and copied into the image. On boot, `seed_if_empty()` loads it when the detections table is empty, so a fresh container comes up with the full library. `/api/health` reports `seed`.
- Regenerate the snapshot after any detection run: `python scripts/export_snapshot.py` (or call `export_snapshot(get_db())`), then commit it. **A detection run that isn't exported does not exist in production.**
- Clip **thumbnails** are stable VideoDB storage URLs, cached in the snapshot-independent `clip_assets` table; they are re-warmed on first request. `python scripts/warm_assets.py` pre-generates them.
- Clip **streams** expire (~24h), so they are never treated as durable: `src/api/clips.py` refreshes any stream older than 18h and the grid fetches them on hover.

If runtime writes ever need to persist (saved reels, user sets), move the catalog to Postgres via `DATABASE_URL` rather than trying to keep SQLite alive.

## Deploy

```bash
railway up
```

Railway builds the `Dockerfile`, which installs the package, copies `src/ web/ docs/recipes/ library/`, and runs:

```
uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT}
```

Healthcheck path: `/api/health`.

## Local

```bash
.venv/bin/python -m uvicorn src.api.app:app --reload --port 8322
```

## Cost notes

VideoDB is billed per unit of work, so the deployed app should only ever *read* cached results:

- scene processing $0.003/scene, transcription $0.01/min, search $1.50/1k queries
- streaming $0.07/GB, MP4 download $0.03/min
- a full describe pass over ~100 videos is roughly $60 — run detection locally, export the snapshot, and let production serve it
