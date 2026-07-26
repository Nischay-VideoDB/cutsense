"""Detect split screen, shake and glitch — within-shot looks, not cut transitions.

Same two-stage shape as the other detectors: a deterministic pixel signal proposes
candidates (free), the model confirms only those.

Usage: python scripts/m2_frame_look.py <videodb_id> [--window 1] [--frames 6] [--dry]
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videodb import SceneExtractionType

from src.catalog.db import add_detection, get_db
from src.detect import frame_look as fl
from src.detect import pipeline as pl
from src.detect.prompts import FRAME_LOOK_PROMPT
from src.videodb_client import get_collection

WORKERS = 12
CONFIRM_CONF = 0.85
LABELS = ("split_screen", "shake", "glitch")


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

    tc = dense_windows(video, window_s, frames)
    windows = tc.scenes
    print(f"{len(windows)} windows of {window_s}s")

    def measure(win):
        urls = [f.url for f in win.frames]
        try:
            split = fl.split_screen_stats(urls)
            shake = fl.shake_stats(urls)
            glitch = fl.glitch_stats(urls)
        except Exception as e:
            return win, None, str(e)[:60]
        hits = []
        if fl.split_screen_plausible(split):
            hits.append(("split_screen", split))
        if fl.shake_plausible(shake):
            hits.append(("shake", shake))
        if fl.glitch_plausible(glitch):
            hits.append(("glitch", glitch))
        return win, hits, None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        measured = list(pool.map(measure, windows))

    candidates = [(w, hits) for w, hits, err in measured if hits]
    tally = {}
    for _w, hits in candidates:
        for label, _ in hits:
            tally[label] = tally.get(label, 0) + 1
    print(f"{len(candidates)} candidate windows  {tally}")
    for w, hits in candidates[:10]:
        print(f"   @{w.start:7.2f}s " + ", ".join(
            f"{label} {stats.get('edge_ratio') or stats.get('displacement') or stats.get('row_anomaly')}"
            for label, stats in hits))
    if dry or not candidates:
        return

    model = pl.resolve_model(candidates[0][0])
    print(f"confirming with model={model}")

    def confirm(item):
        win, hits = item
        try:
            raw = win.describe(prompt=FRAME_LOOK_PROMPT, model_name=model)
            return win, hits, pl.parse_json_reply(raw or "")
        except Exception as e:
            return win, hits, {"label": "unclear", "confidence": 0.0, "evidence": f"error: {e}"}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        confirmed = list(pool.map(confirm, candidates))

    kept = {}
    for win, hits, result in confirmed:
        label = result.get("label")
        proposed = {h[0] for h in hits}
        ok = (label in LABELS and label in proposed
              and float(result.get("confidence") or 0) >= CONFIRM_CONF)
        stored = label if ok else f"rejected:{label}"
        add_detection(db, video_id, -1,
                      {**result, "label": stored,
                       "evidence": f"{result.get('evidence')} [proposed: {', '.join(sorted(proposed))}]"},
                      (win.start, win.end), win.start, pl.PROMPT_VERSION)
        if ok:
            kept[label] = kept.get(label, 0) + 1
            print(f"  {label:13s} @{win.start:7.2f}s conf={result['confidence']} "
                  f"{str(result.get('evidence'))[:56]}")
    print(f"kept: {kept or 'none'} of {len(confirmed)} candidates")


if __name__ == "__main__":
    args = sys.argv[1:]
    win = int(args[args.index("--window") + 1]) if "--window" in args else 1
    fr = int(args[args.index("--frames") + 1]) if "--frames" in args else 6
    main(args[0], win, fr, "--dry" in args)
