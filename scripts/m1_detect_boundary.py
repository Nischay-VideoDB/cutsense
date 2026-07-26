"""M1: run the match-cut and speed-ramp detectors on a video.

These are separate from the shot-start classifier because they need different
windows: match cuts compare frames ACROSS a cut, speed ramps look WITHIN a shot.

Usage:
  python scripts/m1_detect_boundary.py <videodb_id> [--match] [--ramp]
"""

import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import add_detection, get_db, get_frame_desc, put_frame_desc
from src.detect import boundary as bd
from src.detect import pipeline as pl
from src.videodb_client import get_collection

WORKERS = 8
FRAME_PROMPT_TAG = "compo_v1"


def run_match_cuts(coll, video, scenes, db):
    """Frame descriptions are cached in SQLite so judge-prompt iteration is free."""
    started = time.time()

    def describe(frame):
        cached = get_frame_desc(db, frame.id, FRAME_PROMPT_TAG)
        if cached is not None:
            return cached
        desc = frame.describe(prompt=bd.FRAME_COMPO_PROMPT)
        put_frame_desc(db, frame.id, video.id, frame.frame_time, FRAME_PROMPT_TAG, desc)
        return desc

    pairs = [(i, scenes[i - 1], scenes[i]) for i in range(1, len(scenes))
             if (scenes[i - 1].end - scenes[i - 1].start) >= bd.MIN_SHOT_DUR
             and (scenes[i].end - scenes[i].start) >= bd.MIN_SHOT_DUR]

    def work(item):
        i, a, b = item
        try:
            desc_a, desc_b = describe(a.frames[-1]), describe(bd._first_sharp_frame(b))
            raw = coll.generate_text(
                prompt=bd.MATCH_JUDGE_PROMPT.format(desc_a=desc_a, desc_b=desc_b),
                model_name="basic", response_type="json")
            result = raw.get("output", raw) if isinstance(raw, dict) else pl.parse_json_reply(str(raw))
        except Exception as e:
            result = {"label": "unclear", "confidence": 0.0, "evidence": f"error: {e}"}
        return i, b, result

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(work, pairs))

    hits = Counter()
    for i, scene, result in results:
        derived = bd.match_cut_label(result)
        accepted = bd.accepted_boundary(result)
        label = derived if accepted else f"rejected:{derived}"
        add_detection(db, video.id, i, {**result, "label": label},
                      pl.detection_window(scene, getattr(video, "length", scene.end)),
                      scene.start, pl.PROMPT_VERSION)
        if accepted:
            hits[derived] += 1
            print(f"  {derived:13s} @{scene.start:7.2f}s conf={result.get('confidence')}"
                  f"  [{str(result.get('matched_element'))[:40]}]"
                  f"  {str(result.get('evidence'))[:55]}")
    summary = ", ".join(f"{k}={v}" for k, v in sorted(hits.items())) or "none"
    print(f"boundary techniques ({summary}) of {len(results)} cuts in {time.time() - started:.0f}s")


def run_speed_ramps(video, scenes, db):
    started = time.time()
    targets = [(i, s) for i, s in enumerate(scenes) if (s.end - s.start) >= 1.0]

    def work(item):
        i, scene = item
        try:
            raw = scene.describe(prompt=bd.SPEED_RAMP_PROMPT)
            result = pl.parse_json_reply(raw or "")
        except Exception as e:
            result = {"label": "unclear", "confidence": 0.0, "evidence": f"error: {e}"}
        return i, scene, result

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(work, targets))

    hits = 0
    for i, scene, result in results:
        accepted = bd.accepted_speed_ramp(result)
        label = "speed_ramp" if accepted else f"rejected:{result.get('label')}"
        add_detection(db, video.id, i, {**result, "label": label},
                      (scene.start, scene.end), scene.start, pl.PROMPT_VERSION)
        if accepted:
            hits += 1
            print(f"  speed_ramp @{scene.start:7.2f}s conf={result['confidence']}"
                  f"  {result.get('evidence', '')[:80]}")
    print(f"speed ramps: {hits} of {len(results)} shots in {time.time() - started:.0f}s")


if __name__ == "__main__":
    db = get_db()
    coll = get_collection()
    video = coll.get_video(sys.argv[1])
    scenes = pl.extract_shots(video).scenes
    print(f"=== {video.id} | {getattr(video, 'name', '?')} | {len(scenes)} shots")
    do_all = "--match" not in sys.argv and "--ramp" not in sys.argv
    if do_all or "--match" in sys.argv:
        run_match_cuts(coll, video, scenes, db)
    if do_all or "--ramp" in sys.argv:
        run_speed_ramps(video, scenes, db)
