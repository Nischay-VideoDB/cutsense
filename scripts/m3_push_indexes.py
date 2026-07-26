"""Publish every video's detections to VideoDB as a Search V2 technique index.

Makes the detections queryable and aggregatable inside VideoDB itself, rather than
only in our SQLite mirror. Safe to re-run: an existing index of the same name is
replaced, because an index manifest is immutable.

Usage: python scripts/m3_push_indexes.py [--limit N]
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db
from src.catalog.videodb_index import INDEX_NAME, push, records_for
from src.videodb_client import get_collection

WORKERS = 6


def main(limit=None):
    db = get_db()
    coll = get_collection()
    rows = db.execute(
        "SELECT DISTINCT v.videodb_id, v.title FROM videos v"
        " JOIN detections d ON d.videodb_id = v.videodb_id"
        " WHERE v.account='primary'").fetchall()
    if limit:
        rows = rows[:int(limit)]
    print(f"{len(rows)} videos to index as '{INDEX_NAME}'")

    def work(row):
        try:
            records = records_for(db, row["videodb_id"])
            if not records:
                return row, 0, "no detections"
            video = coll.get_video(row["videodb_id"])
            index = push(db, video, records)
            return row, len(records), index.status if index else "skipped"
        except Exception as e:
            return row, 0, f"error: {type(e).__name__}: {str(e)[:80]}"

    ok = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for row, n, status in pool.map(work, rows):
            ok += 1 if n and not status.startswith("error") else 0
            print(f"  {(row['title'] or '')[:42]:42s} {n:3d} records  {status}")
    print(f"\n{ok}/{len(rows)} videos indexed")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[args.index("--limit") + 1] if "--limit" in args else None)
