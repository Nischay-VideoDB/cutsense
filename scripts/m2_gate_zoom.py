"""Apply the scale-jump gate to every zoom-punch detection in the catalog.

The shot-start classifier cannot see a scale jump — the evidence is in the frame pair
either side of the cut — so zoom punches were 14% precise. This re-checks each one
against its own cut and marks the failures refuted. No model calls.

Usage: python scripts/m2_gate_zoom.py [--apply]
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import LOCK, get_db
from src.detect import pipeline as pl
from src.detect import scale_jump as sj
from src.videodb_client import get_collection

WORKERS = 10


def main(apply=False):
    db = get_db()
    rows = db.execute(
        "SELECT d.id, d.videodb_id, d.cut_time_s, d.verified, v.account FROM detections d"
        " JOIN videos v ON v.videodb_id = d.videodb_id"
        " WHERE d.technique='zoom_punch' AND (d.verified IS NULL OR d.verified = 1)").fetchall()
    print(f"{len(rows)} visible zoom punches to gate")

    cache = {}

    def check(row):
        key = (row["account"] or "primary", row["videodb_id"])
        try:
            if key not in cache:
                video = get_collection(account=key[0]).get_video(row["videodb_id"])
                cache[key] = pl.extract_shots(video).scenes
            scenes = cache[key]
            idx = min(range(len(scenes)), key=lambda i: abs(scenes[i].start - row["cut_time_s"]))
            if idx == 0:
                return row, None, "no preceding shot"
            stats = sj.scale_jump_stats(scenes[idx - 1].frames[-1].url, scenes[idx].frames[0].url)
            ok = sj.scale_jump_plausible(stats)
            return row, ok, f"scale {stats['scale']}x {stats['direction']}, gain {stats['gain']}"
        except Exception as e:
            return row, None, f"error: {type(e).__name__}"

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(check, rows))

    keep = [r for r, ok, _ in results if ok]
    drop = [(r, why) for r, ok, why in results if ok is False]
    skip = [r for r, ok, _ in results if ok is None]
    print(f"  keep {len(keep)} · reject {len(drop)} · could not judge {len(skip)}")
    for row, why in drop[:8]:
        print(f"    reject #{row['id']} @{row['cut_time_s']:.2f}s  {why}")

    if apply and drop:
        with LOCK:
            db.executemany(
                "UPDATE detections SET verified=0, verify_note=? WHERE id=?",
                [(f"refuted: no scale jump across the cut ({why})", row["id"])
                 for row, why in drop])
            db.commit()
        print(f"\nmarked {len(drop)} refuted")
    elif not apply:
        print("\ndry run — re-run with --apply")


if __name__ == "__main__":
    main("--apply" in sys.argv)
