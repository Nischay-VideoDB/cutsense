"""M1: run detection pipeline on a video (or every un-scanned video in the collection).

Usage:
  python scripts/m1_detect.py <videodb_id> [--threshold 20] [--serial]
  python scripts/m1_detect.py --all          # skips videos already scanned
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import add_detection, get_db, upsert_video
from src.detect import pipeline as pl
from src.videodb_client import get_collection


def already_scanned(db, videodb_id):
    return db.execute(
        "SELECT COUNT(*) c FROM detections WHERE videodb_id=? AND prompt_version=?",
        [videodb_id, pl.PROMPT_VERSION]).fetchone()["c"] > 0


def run(video, db, threshold=20, parallel=True):
    started = time.time()
    print(f"\n=== {video.id} | {getattr(video, 'name', '?')}")
    upsert_video(db, video.id, title=getattr(video, "name", None),
                 duration_s=float(getattr(video, "length", 0)))
    sc = pl.extract_shots(video, threshold=threshold)
    scenes = sc.scenes
    print(f"{len(scenes)} shots (threshold={threshold}, sc={sc.id})")
    db.executemany(
        "INSERT OR IGNORE INTO shots (videodb_id, scene_collection_id, idx, start_s, end_s)"
        " VALUES (?,?,?,?,?)",
        [(video.id, sc.id, i, s.start, s.end) for i, s in enumerate(scenes)])
    db.commit()

    results = (pl.classify_shots_parallel(sc) if parallel else list(pl.classify_shots(sc)))
    accepted, vetoed = [], []
    for i, scene, result in results:
        window = pl.detection_window(scene, getattr(video, "length", scene.end))
        ok, reason = pl.validate_detection(scene, result)
        if ok:
            add_detection(db, video.id, i, result, window, scene.start, pl.PROMPT_VERSION)
            accepted.append((scene.start, result["label"], result["confidence"]))
        else:
            if reason != "below_confidence":
                vetoed.append((scene.start, result["label"], result["confidence"], reason))
            add_detection(db, video.id, i, {**result, "label": f"rejected:{result.get('label')}",
                                            "evidence": reason},
                          window, scene.start, pl.PROMPT_VERSION)

    print(f"accepted {len(accepted)} of {len(results)} shots in {time.time() - started:.0f}s")
    for start, label, conf in accepted:
        print(f"  @{start:7.2f}s  {label:10s} conf={conf}")
    for start, label, conf, reason in vetoed:
        print(f"  @{start:7.2f}s  VETOED {label} conf={conf} ({reason})")


if __name__ == "__main__":
    db = get_db()
    coll = get_collection()
    threshold = 20
    if "--threshold" in sys.argv:
        threshold = int(sys.argv[sys.argv.index("--threshold") + 1])
    parallel = "--serial" not in sys.argv

    if "--all" in sys.argv:
        for v in coll.get_videos():
            if already_scanned(db, v.id):
                print(f"skip (scanned): {v.id} {getattr(v, 'name', '')[:40]}")
                continue
            run(v, db, threshold, parallel)
    else:
        run(coll.get_video(sys.argv[1]), db, threshold, parallel)
