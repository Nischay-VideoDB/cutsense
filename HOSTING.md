# Hosting CutSense

## Public deployment — Vercel + Azure PostgreSQL

The production app is <https://cutsense-three.vercel.app>. Vercel routes the entire application
through the FastAPI function with a long-running-function budget for real VideoDB analysis. The
original SPA and all client-owned deep links remain reload-safe.

Azure PostgreSQL is the durable catalog for submitted analyses, shots, detections, generated clip
assets, and study reels. The connection adapter uses a bounded, serverless-safe pool (minimum
zero, maximum four by default) and statement-scoped checkouts. The tracked 46-video snapshot
seeds an empty database once; new live runs remain independent and survive deploys.

The public application exposes the original URL workflow:

- Paste a public video URL, run VideoDB ingest/shot extraction/detection synchronously, and poll or
  reopen the durable analysis record.
- Browse reports, technique recipes, creator/video profiles, public examples, and exact clips.
- Compile a VideoDB HLS study reel and request an MP4 download. Repeated reel requests are
  idempotent, and expiring signed download links are refreshed when necessary.

Private/local addresses are rejected, input length is bounded, and cost-bearing analysis, reel,
and export operations have separate hashed-visitor hourly limits. Repeating an already-complete
URL or reel returns its durable result without spending the rate or provider budget again.

## Local operator workflow

The same FastAPI application runs locally for operator work. Local mode keeps the original direct
file-upload path and uses SQLite by default; production never uses SQLite or an ephemeral local
file as authoritative state.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Set VIDEO_DB_API_KEY only in the local .env.
.venv/bin/python -m uvicorn src.api.app:app --port 8322
```

`library/catalog-snapshot.json` remains the reviewed seed corpus. After an intentional local
detection pass, validate it and run `python scripts/export_snapshot.py`; review and commit the
new snapshot before changing the prepared corpus.

## Cost and state boundaries

VideoDB ingest, fresh analysis, streaming, timeline rendering, and MP4 downloads are paid
operations. Production credentials remain server-side. PostgreSQL stores idempotency and rate
records; Vercel functions do not rely on background threads, process memory, SQLite, or mutable
local files for production state. Direct serverless uploads are rejected because their bytes
would be ephemeral; use a durable public URL in the hosted demo.
