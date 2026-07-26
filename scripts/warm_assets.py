"""Pre-generate thumbnails for every shipping detection so the UI never waits.

Thumbnails are stable storage URLs, so warming them once is permanent; streams are
deliberately left to be generated on demand because they expire.

Usage: python scripts/warm_assets.py [--streams]
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api import clips as clip_service
from src.catalog.db import get_db
from src.detect.prompts import SHIPPING_TECHNIQUES

WORKERS = 8


def main(with_streams=False):
    db = get_db()
    rows = db.execute(
        "SELECT d.*, v.account FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
        f" WHERE d.technique IN ({','.join('?' * len(SHIPPING_TECHNIQUES))})",
        SHIPPING_TECHNIQUES).fetchall()
    print(f"warming {len(rows)} detections (streams={with_streams})")

    done = {"ok": 0, "fail": 0}

    def work(row):
        try:
            clip_service.clip_assets(db, row, account=row["account"] or "primary",
                                     want_stream=with_streams)
            done["ok"] += 1
        except Exception as e:
            done["fail"] += 1
            print(f"  {row['id']} failed: {type(e).__name__}: {e}")
        if (done["ok"] + done["fail"]) % 20 == 0:
            print(f"  {done['ok'] + done['fail']}/{len(rows)}")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, rows))
    print(f"done: {done['ok']} ok, {done['fail']} failed")


if __name__ == "__main__":
    main("--streams" in sys.argv)
