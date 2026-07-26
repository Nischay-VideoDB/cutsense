"""Speed-ramp detection: dense motion sampling, then VLM confirmation.

Why it replaces the old detector: the shot-level pass sampled 3 frames per shot and
found zero ramps across the whole library, because a velocity change is invisible in
three stills. Here we extract 1s windows at 6 frames, measure frame-to-frame motion
locally (free), and only ask the model about windows whose motion actually swings.

Usage:
  python scripts/m2_speed_ramp.py <videodb_id> [--window 1] [--frames 6] [--dry]
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videodb import SceneExtractionType

from src.catalog.db import add_detection, get_db
from src.detect import motion
from src.detect import pipeline as pl
from src.videodb_client import get_collection

WORKERS = 8
CONFIRM_CONF = 0.8

CONFIRM_PROMPT = """These frames are consecutive samples from ONE continuous shot (no cuts).
Measured frame-to-frame movement inside this window swings widely, which usually means
the playback speed changes mid-shot.

Judge whether this is a SPEED RAMP: the same continuous action played at two different
speeds (slow motion snapping to fast, or fast dropping into slow).

Signs it is a ramp: some consecutive frames are nearly identical while others jump far
apart, motion blur on the same subject changes abruptly, or a subject's motion arc is
unevenly spaced.
Signs it is NOT: the subject simply starts or stops moving, the camera whips, or a new
object enters the frame. Natural changes in the action are not speed changes.

Respond ONLY with JSON:
{"label": "<speed_ramp|constant_speed|unclear>", "confidence": <0.0-1.0>, "evidence": "<one short sentence>"}"""


def dense_windows(video, window_s, frames):
    try:
        return video.extract_scenes(
            extraction_type=SceneExtractionType.time_based,
            extraction_config={"time": window_s, "frame_count": frames})
    except Exception as e:
        if "already exists" not in str(e):
            raise
        return video.get_scene_collection(pl.existing_collection_id(e))


def main(video_id, window_s=1, frames=6, dry=False):
    db = get_db()
    coll = get_collection()
    video = coll.get_video(video_id)
    print(f"=== {video_id} | {getattr(video, 'name', '?')}")

    shots = pl.extract_shots(video).scenes
    tc = dense_windows(video, window_s, frames)
    inside = motion.windows_inside_shots(tc.scenes, shots)
    print(f"{len(shots)} shots · {len(tc.scenes)} windows of {window_s}s · "
          f"{len(inside)} windows sit inside a single shot")

    def measure(item):
        win, shot = item
        try:
            series = motion.motion_series([f.url for f in win.frames])
            return win, shot, motion.ramp_stats(series)
        except Exception as e:
            return win, shot, {"usable": False, "reason": str(e)[:60]}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        measured = list(pool.map(measure, inside))

    candidates = [(w, s, st) for w, s, st in measured if motion.ramp_plausible(st)]
    print(f"{len(candidates)} motion candidates (ratio >= {motion.RAMP_MIN_RATIO})")
    for w, _s, st in candidates[:12]:
        print(f"   @{w.start:7.2f}s step={st['step_ratio']:5.1f} spike={st['spike_share']:.2f} "
              f"{'accel' if st['accelerating'] else 'decel'} motion={st['motion']}")
    if dry or not candidates:
        return

    model = pl.resolve_model(candidates[0][0])
    print(f"confirming with model={model}")

    def confirm(item):
        win, shot, st = item
        try:
            raw = win.describe(prompt=CONFIRM_PROMPT, model_name=model)
            return win, shot, st, pl.parse_json_reply(raw or "")
        except Exception as e:
            return win, shot, st, {"label": "unclear", "confidence": 0.0,
                                   "evidence": f"error: {e}"}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        confirmed = list(pool.map(confirm, candidates))

    kept = 0
    for win, shot, st, result in confirmed:
        ok = (result.get("label") == "speed_ramp"
              and float(result.get("confidence") or 0) >= CONFIRM_CONF)
        label = "speed_ramp" if ok else f"rejected:{result.get('label')}"
        add_detection(db, video_id, -1,
                      {**result, "label": label,
                       "evidence": f"{result.get('evidence')} [ratio {st['ratio']}]"},
                      (win.start, win.end), win.start, pl.PROMPT_VERSION)
        if ok:
            kept += 1
            print(f"  speed_ramp @{win.start:7.2f}s conf={result['confidence']} "
                  f"ratio={st['ratio']}  {str(result.get('evidence'))[:60]}")
    print(f"speed ramps kept: {kept} of {len(confirmed)} candidates")


if __name__ == "__main__":
    args = sys.argv[1:]
    win = int(args[args.index("--window") + 1]) if "--window" in args else 1
    fr = int(args[args.index("--frames") + 1]) if "--frames" in args else 6
    main(args[0], win, fr, "--dry" in args)
