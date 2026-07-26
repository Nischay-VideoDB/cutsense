"""Experiment: let the VLM SEE both sides of a cut instead of reading descriptions.

Why: the text-description match-cut judge has a recall problem — descriptions throw
away the visual specifics a match cut is built from. Scene.describe() needs a
server-side scene id, so we can't hand it an arbitrary frame pair.

Trick: extract a SECOND, time-based scene collection with short windows. Any window
that straddles a cut contains frames from both shots, and it has a real scene id, so
describe() works and the model sees both images at once.

Usage: python scripts/m1_exp_paired_vision.py <videodb_id> [--time 2] [--limit 25]
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videodb import SceneExtractionType

from src.detect import pipeline as pl
from src.videodb_client import get_collection

EDGE_MARGIN = 0.35   # a cut this close to a window edge is poorly covered
WORKERS = 8

PAIRED_PROMPT = """These frames are consecutive moments from one short window of an edited video.
A CUT happens somewhere inside this window: the early frames belong to one shot and the
later frames belong to the next shot.

Look at the frames before the cut and the frames after it, then answer:

1. same_context: do both sides show the SAME location/scene, or one subject continuing
one action? Two angles of one ongoing scene = true. A genuinely different place, subject
or subject matter = false.

2. composition_match: is a SPECIFIC concrete visual element deliberately carried across
the cut — the same dominant shape or silhouette, the same screen position of the main
form, the same distinctive framing geometry, or a motion direction that continues into
the next shot? Generic similarity ("both dark", "both centered") does NOT count. Answer
false unless you can name the specific element.

Respond ONLY with JSON:
{"same_context": <true|false>, "composition_match": <true|false>,
 "matched_element": "<specific element or empty>", "confidence": <0.0-1.0>,
 "evidence": "<one short sentence>"}"""


def windows_covering_cuts(time_scenes, cut_times):
    """Pick time windows that contain a cut comfortably inside them."""
    picked = []
    for scene in time_scenes:
        inside = [t for t in cut_times
                  if scene.start + EDGE_MARGIN <= t <= scene.end - EDGE_MARGIN]
        if inside:
            picked.append((scene, inside[0]))
    return picked


def main(video_id, window_s=2, limit=25):
    coll = get_collection()
    video = coll.get_video(video_id)

    shot_scenes = pl.extract_shots(video).scenes
    cut_times = [s.start for s in shot_scenes[1:]]
    print(f"{len(cut_times)} cuts from shot detection")

    try:
        tc = video.extract_scenes(
            extraction_type=SceneExtractionType.time_based,
            extraction_config={"time": window_s, "frame_count": 4})
    except Exception as e:
        if "already exists" not in str(e):
            raise
        import re
        sc_id = re.search(r"id (\S+?)\.?$", str(e)).group(1)
        tc = video.get_scene_collection(sc_id)
    print(f"time-based collection {tc.id}: {len(tc.scenes)} windows of {window_s}s")

    targets = windows_covering_cuts(tc.scenes, cut_times)[:limit]
    print(f"{len(targets)} windows straddle a cut (showing up to {limit})\n")

    def work(item):
        scene, cut = item
        try:
            raw = scene.describe(prompt=PAIRED_PROMPT)
            return cut, pl.parse_json_reply(raw or "")
        except Exception as e:
            return cut, {"label": "error", "evidence": str(e)}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(work, targets))

    hits = 0
    for cut, r in results:
        is_match = r.get("composition_match") and r.get("same_context") is False
        if is_match:
            hits += 1
        flag = "MATCH_CUT" if is_match else "         "
        print(f"  @{cut:7.2f}s {flag} ctx={str(r.get('same_context'))[:5]:5s}"
              f" compo={str(r.get('composition_match'))[:5]:5s} conf={r.get('confidence')}"
              f"  {str(r.get('matched_element') or r.get('evidence'))[:60]}")
    print(f"\npaired-vision match cuts: {hits} of {len(results)} cuts examined")


if __name__ == "__main__":
    args = sys.argv[1:]
    window = int(args[args.index("--time") + 1]) if "--time" in args else 2
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 25
    main(args[0], window, limit)
