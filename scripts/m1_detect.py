"""M1: run detection pipeline on a video (or all videos in the collection).

Usage:
  python scripts/m1_detect.py <videodb_id> [--threshold 20]
  python scripts/m1_detect.py --all
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import add_detection, get_db, upsert_video
from src.detect import pipeline as pl
from src.videodb_client import get_collection


def run(video, db, threshold=20):
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

    accepted = 0
    for i, scene, result in pl.classify_shots(sc):
        window = pl.detection_window(scene, getattr(video, "length", scene.end))
        add_detection(db, video.id, i, result, window, scene.start, pl.PROMPT_VERSION)
        mark = ""
        if pl.is_accepted(result):
            accepted += 1
            mark = "  <-- DETECTION"
        print(f"  shot {i} @{scene.start:7.2f}s  {result.get('label', '?'):10s}"
              f" conf={result.get('confidence', 0)}{mark}")
    print(f"accepted detections: {accepted}")


if __name__ == "__main__":
    db = get_db()
    coll = get_collection()
    threshold = 20
    if "--threshold" in sys.argv:
        threshold = int(sys.argv[sys.argv.index("--threshold") + 1])
    if "--all" in sys.argv:
        for v in coll.get_videos():
            run(v, db, threshold)
    else:
        run(coll.get_video(sys.argv[1]), db, threshold)
