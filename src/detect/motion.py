"""Motion series from frames — the signal a speed ramp actually leaves behind.

A speed ramp changes how far the image travels between consecutive frames while
the shot stays continuous. Three frames per shot cannot show that; six frames in a
one-second window can. So we sample densely, measure frame-to-frame displacement,
and look for an abrupt change in that series inside a single shot.

This is deterministic and costs no model calls — the VLM is only asked to confirm
candidates, the same shape as the whip-pan pixel gate.
"""

import numpy as np

from src.detect.filters import load_gray

# calibrated on library footage: a ramp shows a large swing between the quietest
# and busiest consecutive-frame motion inside one continuous shot
RAMP_MIN_RATIO = 3.0        # max(motion) / max(min(motion), floor)
RAMP_MIN_MOTION = 1.5       # ignore near-static windows; nothing is ramping
RAMP_MIN_FRAMES = 4
MOTION_FLOOR = 0.35         # keeps the ratio finite on very still frames

# A ramp is a SUSTAINED change in how fast the image moves. A single frame carrying
# most of the movement is a whip pan or an impact frame, not a speed change — that
# distinction is what the raw max/min ratio misses.
RAMP_MIN_STEP = 2.5         # slower half vs faster half of the window
RAMP_MAX_SPIKE_SHARE = 0.62  # fraction of all motion in one frame pair


def motion_series(frame_urls, max_side=240):
    """Mean absolute pixel change between consecutive frames, in order."""
    grays = [load_gray(u, max_side=max_side) for u in frame_urls]
    series = []
    for a, b in zip(grays, grays[1:]):
        if a.shape != b.shape:
            h = min(a.shape[0], b.shape[0])
            w = min(a.shape[1], b.shape[1])
            a, b = a[:h, :w], b[:h, :w]
        series.append(float(np.abs(a - b).mean()))
    return series


def ramp_stats(series):
    if len(series) < RAMP_MIN_FRAMES - 1:
        return {"usable": False, "reason": "too few frames"}
    hi, lo = max(series), max(min(series), MOTION_FLOOR)
    ratio = hi / lo
    # where the biggest step happens, as a fraction through the window
    steps = [abs(b - a) for a, b in zip(series, series[1:])]
    break_at = (steps.index(max(steps)) + 1) / len(series) if steps else None

    total = sum(series) or 1e-6
    spike_share = hi / total
    half = len(series) // 2 or 1
    first, second = series[:half], series[half:]
    mean_first = sum(first) / len(first)
    mean_second = sum(second) / len(second)
    slow, fast = sorted((max(mean_first, MOTION_FLOOR), max(mean_second, MOTION_FLOOR)))
    return {
        "usable": True,
        "motion": [round(v, 2) for v in series],
        "peak_motion": round(hi, 2),
        "quiet_motion": round(min(series), 2),
        "ratio": round(ratio, 2),
        "step_ratio": round(fast / slow, 2),
        "spike_share": round(spike_share, 2),
        "break_at": round(break_at, 2) if break_at is not None else None,
        "accelerating": bool(mean_second > mean_first),
    }


def ramp_plausible(stats):
    """Candidate gate: real motion, a sustained step in it, and not a one-frame spike."""
    if not stats.get("usable"):
        return False
    return (stats["peak_motion"] >= RAMP_MIN_MOTION
            and stats["ratio"] >= RAMP_MIN_RATIO
            and stats["step_ratio"] >= RAMP_MIN_STEP
            and stats["spike_share"] <= RAMP_MAX_SPIKE_SHARE)


def windows_inside_shots(time_scenes, shot_scenes, margin=0.25):
    """Time windows that sit wholly inside one shot — no cut, so motion is comparable."""
    bounds = [(s.start, s.end) for s in shot_scenes]
    picked = []
    for w in time_scenes:
        for start, end in bounds:
            if w.start >= start - margin and w.end <= end + margin:
                picked.append((w, (start, end)))
                break
    return picked
