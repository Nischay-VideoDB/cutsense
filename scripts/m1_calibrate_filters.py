"""Calibrate the whip-pan pixel filter against hand-verified shots.

Truth comes from visual inspection during M0/M1 spot-checks. Each case is a shot
in a real scene collection, so the filter sees exactly what production sees.
Usage: python scripts/m1_calibrate_filters.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.detect.filters import shot_whip_stats, whip_plausible
from src.videodb_client import get_collection

CLASSROOM = "m-z-019f9a8e-a38d-7f23-b961-8f9c3da96a20"
TUTORIAL = "m-z-019f9a8e-dd77-7510-a4fb-c1c298b656af"
ASD = "m-z-019f9aab-eff6-7ad1-a6a4-e3c6cf179086"
IKEA = "m-z-019f9b02-d584-7a03-9f78-fe1f11e1e3ec"

# (video_id, shot_start_s, truth) — truth verified by eye
CASES = [
    (CLASSROOM, 1.40, "whip"),
    (CLASSROOM, 3.56, "whip"),
    (CLASSROOM, 2.96, "not_whip"),
    (TUTORIAL, 34.00, "whip"),
    (TUTORIAL, 50.50, "whip"),
    (TUTORIAL, 97.92, "whip"),
    (TUTORIAL, 4.58, "not_whip"),
    (ASD, 204.36, "whip"),
    (ASD, 121.44, "not_whip"),   # STOP sign; VLM said whip 0.97
    (IKEA, 6.40, "not_whip"),    # blurred arm, sharp hallway; VLM said whip 0.98
    (IKEA, 9.80, "whip"),
]


def main():
    coll = get_collection()
    cache = {}
    print(f"{'video':10s} {'@s':>8s} {'truth':9s} {'first_sh':>9s} {'settled':>9s} {'ratio':>7s}  verdict")
    wrong = 0
    for video_id, start, truth in CASES:
        if video_id not in cache:
            v = coll.get_video(video_id)
            cache[video_id] = v.get_scene_collection("st20m15f3").scenes
        scene = min(cache[video_id], key=lambda s: abs(s.start - start))
        first, settled = shot_whip_stats(scene)
        verdict = "whip" if whip_plausible(first, settled) else "not_whip"
        ratio = (settled["sharpness"] / max(first["sharpness"], 1e-6)) if settled else float("nan")
        wrong += verdict != truth
        print(f"{video_id[-8:]:10s} {start:8.2f} {truth:9s} {first['sharpness']:9.1f} "
              f"{(settled['sharpness'] if settled else 0):9.1f} {ratio:7.2f}  {verdict:9s}"
              f" {'ok' if verdict == truth else 'MISMATCH'}")
    print(f"\n{len(CASES) - wrong}/{len(CASES)} correct")


if __name__ == "__main__":
    main()
