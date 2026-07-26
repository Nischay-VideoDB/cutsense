"""Batch-ingest library videos from library/eyecannndy/manifest.json into VideoDB.

Resumable: skips videos already in the catalog. YouTube sources only for now.
Usage: python scripts/ingest_batch.py [N]   # ingest up to N videos (default 5)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db, upsert_video
from src.videodb_client import get_collection

MANIFEST = Path(__file__).resolve().parents[1] / "library" / "eyecannndy" / "manifest.json"


def main(limit=5):
    db = get_db()
    coll = get_collection()
    manifest = json.loads(MANIFEST.read_text())["videos"]
    done_urls = {r["source_url"] for r in db.execute(
        "SELECT source_url FROM videos WHERE source_url IS NOT NULL AND account='primary'")}

    # densest multi-technique videos first (manifest is pre-sorted by clip count)
    todo = [v for v in manifest
            if "youtu" in v["src"] and v["src"] not in done_urls][:limit]
    print(f"{len(todo)} videos to ingest (limit {limit})")

    for v in todo:
        hint = ",".join(v["techniques"])
        print(f"\nuploading: {v['title'][:60]}  [{hint}]")
        try:
            vid = coll.upload(url=v["src"])
        except Exception as e:
            print("  FAILED:", e)
            continue
        upsert_video(db, vid.id, title=getattr(vid, "name", v["title"]), source_url=v["src"],
                     technique_hint=hint, duration_s=float(getattr(vid, "length", 0)))
        print(f"  -> {vid.id}  {getattr(vid, 'length', '?')}s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
