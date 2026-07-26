# Hosting CutSense

Target: **Railway** (Docker build, auto-deploy from `main` on `github.com/falgunitripathi`).

## Environment

| Var | Required | Purpose |
|---|---|---|
| `VIDEO_DB_API_KEY` | yes | project VideoDB account (Falgunitripathi8) |
| `VIDEO_DB_API_KEY_LEGACY` | only while legacy assets are served | earlier account holding the first calibration videos |
| `PORT` | injected | Railway sets this; the CMD expands it |
| `RAILWAY_GIT_COMMIT_SHA` | injected | reported by `/api/health` as `version` |

## Persisting visitor-submitted analyses (needed for the public gallery)

The gallery lists every analysed video, including ones visitors submit. Those rows are
written at runtime, so they need storage that outlives the container.

`CUTSENSE_DB` points the catalog anywhere, so the simplest durable setup is a Railway
volume — no database port, no SQL dialect risk:

1. Add a volume to the service, mount path `/data`.
2. Set `CUTSENSE_DB=/data/cutsense.sqlite`.
3. Redeploy. On first boot the snapshot seeds the volume, and every later analysis
   accumulates there.

Postgres is the alternative if several instances ever need to share state; that
requires porting the catalog's SQL (SQLite-specific `INSERT OR IGNORE`,
`COUNT(...) FILTER`, `datetime('now')`, `AUTOINCREMENT`), so the volume is the
better trade until horizontal scale is actually needed.

### CLI access note

The Railway CLI is installed at `~/.hermes/node/bin/railway` and is logged in as
`thelonelyrulershiv@gmail.com`, whose workspace contains an unrelated project only.
The CutSense project (`c7dde329-6a33-4e50-ac61-e098961076ba`) is not in that
workspace, so the CLI cannot reach it until either that account is added to the
project, `railway login` is run as the owning account, or a project token is
exported as `RAILWAY_TOKEN`.

## What survives a redeploy — and what doesn't

The container filesystem is **ephemeral**. `data/cutsense.sqlite` is written at runtime and is gitignored, so a redeploy starts with an empty database.

That is handled deliberately:

- `library/catalog-snapshot.json` is **git-tracked** and copied into the image. On boot, `seed_if_empty()` loads it when the detections table is empty, so a fresh container comes up with the full library. `/api/health` reports `seed`.
- Regenerate the snapshot after any detection run: `python scripts/export_snapshot.py` (or call `export_snapshot(get_db())`), then commit it. **A detection run that isn't exported does not exist in production.**
- Clip **thumbnails** are stable VideoDB storage URLs, cached in the snapshot-independent `clip_assets` table; they are re-warmed on first request. `python scripts/warm_assets.py` pre-generates them.
- Clip **streams** expire (~24h), so they are never treated as durable: `src/api/clips.py` refreshes any stream older than 18h and the grid fetches them on hover.

If runtime writes ever need to persist (saved reels, user sets), move the catalog to Postgres via `DATABASE_URL` rather than trying to keep SQLite alive.

## Deploy

Railway builds the `Dockerfile`: dependencies from `requirements.txt` first (so code edits keep the install layer cached), then `src/ web/ docs/recipes/ library/`, then:

```
uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT}
```

Healthcheck path: `/api/health`. Set `VIDEO_DB_API_KEY` in the service variables before the first browse.

**The package is deliberately not installed.** The app runs from the working directory, so `pip install .` would only add a build step that needs `src/` present in the dependency layer — which is exactly what broke the first build (`error: package directory 'src' does not exist`, because `pip install .` ran before `COPY src ./src`).

### Verifying a deploy without Docker locally

The image layout can be reproduced with plain file copies, which catches missing files and unset-variable behaviour:

```bash
rm -rf /tmp/imgtest && mkdir -p /tmp/imgtest/docs
cp -R src web library /tmp/imgtest/ && cp -R docs/recipes /tmp/imgtest/docs/
cd /tmp/imgtest && env -u VIDEO_DB_API_KEY <path-to>/.venv/bin/python -m uvicorn src.api.app:app --port 8399
```

Expected with no key set: `/api/health`, `/`, `/api/clips`, `/api/thumb/{id}` and `/api/recipes/{t}` all succeed (thumbnails come from the snapshot), and `/api/clips/{id}/stream` returns **503 "playback unavailable"** — not a 500.

### Networking

`cutsense.railway.internal` is the **private** hostname for service-to-service traffic inside the Railway project; a browser cannot reach it. For public access, generate a domain on the service (`railway domain`, or Settings → Networking → Generate Domain) and use that URL.

## Local

```bash
.venv/bin/python -m uvicorn src.api.app:app --reload --port 8322
```

## Cost notes

VideoDB is billed per unit of work, so the deployed app should only ever *read* cached results:

- scene processing $0.003/scene, transcription $0.01/min, search $1.50/1k queries
- streaming $0.07/GB, MP4 download $0.03/min
- a full describe pass over ~100 videos is roughly $60 — run detection locally, export the snapshot, and let production serve it
