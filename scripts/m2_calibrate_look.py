"""Calibrate the split-screen / shake / glitch gates from the real distribution.

Guessed thresholds fired on 160 of 161 windows. With no labelled examples, the
defensible alternative is to treat these looks as rare by construction: sample many
windows from ordinary footage and set each gate near the top of the distribution, so
only genuine outliers reach the model.

Usage: python scripts/m2_calibrate_look.py [--windows 40] [--videos 4]
"""

import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videodb import SceneExtractionType

from src.catalog.db import get_db
from src.detect import frame_look as fl
from src.detect import pipeline as pl
from src.videodb_client import get_collection

WORKERS = 12
PERCENTILES = (0.5, 0.9, 0.98, 0.995)


def pct(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))], 2)


def main(per_video=40, video_count=4):
    db = get_db()
    coll = get_collection()
    vids = db.execute(
        "SELECT videodb_id, title FROM videos WHERE account='primary'"
        " AND duration_s BETWEEN 60 AND 220 ORDER BY rowid LIMIT ?", [video_count]).fetchall()

    samples = {"edge_ratio": [], "persistence": [], "displacement": [],
               "reversals": [], "row_anomaly": [], "torn_rows": []}

    for v in vids:
        video = coll.get_video(v["videodb_id"])
        try:
            tc = video.extract_scenes(
                extraction_type=SceneExtractionType.time_based,
                extraction_config={"time": 1, "frame_count": 6})
        except Exception as e:
            if "already exists" not in str(e):
                print(f"  skip {v['title'][:30]}: {e}")
                continue
            tc = video.get_scene_collection(pl.existing_collection_id(e))
        windows = tc.scenes[:per_video]
        print(f"{(v['title'] or '')[:44]:44s} sampling {len(windows)} windows")

        def measure(win):
            urls = [f.url for f in win.frames]
            try:
                return (fl.split_screen_stats(urls), fl.shake_stats(urls), fl.glitch_stats(urls))
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for got in pool.map(measure, windows):
                if not got:
                    continue
                split, shake, glitch = got
                if split.get("usable"):
                    samples["edge_ratio"].append(split["edge_ratio"])
                    samples["persistence"].append(split["persistence"])
                if shake.get("usable"):
                    samples["displacement"].append(shake["displacement"])
                    samples["reversals"].append(shake["reversals"])
                if glitch.get("usable"):
                    samples["row_anomaly"].append(glitch["row_anomaly"])
                    samples["torn_rows"].append(glitch["torn_rows"])

    print(f"\n{len(samples['row_anomaly'])} windows measured\n")
    print(f"{'metric':14s} " + " ".join(f"p{int(p*1000)/10:<6}" for p in PERCENTILES) + "  max")
    for name, values in samples.items():
        if not values:
            continue
        row = " ".join(f"{pct(values, p)!s:<7}" for p in PERCENTILES)
        print(f"{name:14s} {row}  {max(values)}")
    print("\nSuggested gates (p99.5, so these looks stay rare):")
    print(f"  SPLIT_MIN_EDGE_RATIO      = {pct(samples['edge_ratio'], 0.995)}")
    print(f"  SHAKE_MIN_DISPLACEMENT    = {pct(samples['displacement'], 0.995)}")
    print(f"  GLITCH_MIN_ROW_ANOMALY    = {pct(samples['row_anomaly'], 0.995)}")
    print(f"  GLITCH_MIN_TORN_ROWS      = {pct(samples['torn_rows'], 0.995)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    w = int(args[args.index("--windows") + 1]) if "--windows" in args else 40
    n = int(args[args.index("--videos") + 1]) if "--videos" in args else 4
    main(w, n)
