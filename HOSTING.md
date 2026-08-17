# Hosting CutSense

## Public deployment - Vercel prepared demo

The only public deployment target is the static Vercel demo in `showcase/`.
`vercel.json` uses that directory as its output and rewrites the client-side routes
to `index.html`, so `/`, `/library`, `/video/<slug>`, and `/clip/<id>` remain
reload-safe.

The prepared demo has no server functions, credentials, upload control, fresh
analysis path, VideoDB query, stream regeneration, or reel generation. Its content is
a small provenance-labelled subset of `library/catalog-snapshot.json`:

- Video IDs, detection evidence, timestamps, scores, and thumbnails come from the
  tracked VideoDB-backed snapshot.
- Cached thumbnails may be displayed as static image URLs.
- Clip and study-reel playback is explicitly unavailable unless a durable cached URL is
  committed. The current snapshot contains none, and the public demo will not create one.

Deploy only the prepared static project after review. It requires no environment
variables or persistent database.

## Local operator workflow

The original FastAPI application remains available for an authenticated operator, not
for public deployment. It is the workflow that ingests media, extracts shot boundaries,
classifies techniques, refreshes clip streams, and compiles study reels.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Set VIDEO_DB_API_KEY only in the local .env.
.venv/bin/python -m uvicorn src.api.app:app --port 8322
```

`library/catalog-snapshot.json` is the handoff between the operator workflow and the
public prepared demo. After an intentional local detection pass, validate it and run
`python scripts/export_snapshot.py`; review and commit the new snapshot before exposing
any updated prepared data.

## Cost and state boundaries

VideoDB ingest, fresh analysis, streaming, and timeline rendering are paid operations.
They must remain in the credentialed local workflow with its existing catalog and
operator review. A Vercel public deployment never writes the catalog or relies on a
mutable shared filesystem or job runner.
