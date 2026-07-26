"""Detect a scale jump across a cut by comparing the two frames that flank it.

A zoom punch cannot be judged from the incoming shot alone — radial blur is produced
by any fast forward camera move, which is exactly what the shot-start classifier kept
mistaking for a punch (129 of 150 detections refuted). The evidence for a punch lives
in the *pair*: shot B looks like a magnified (or widened) crop of shot A.

So test that directly: crop A's centre by 1/s, resize to B, and correlate. If some
s > 1 matches materially better than s = 1, the framing jumped scale at the cut.
Deterministic, no model call, and calibratable against the audited labels.
"""

import numpy as np

from src.detect.filters import load_gray

SCALES = (1.12, 1.25, 1.4, 1.6, 1.9)
# Calibrated against the 51 audited zoom-punch labels: gain>=0.15 with corr>=0.35 keeps
# 9/21 confirmed punches while rejecting 27/30 false ones — 75% precision, up from 14%.
# Recall is deliberately the thing sacrificed: a missing punch is invisible, a wrong one
# is on screen.
MIN_GAIN = 0.15
MIN_CORRELATION = 0.35


def _center_crop(gray, factor):
    """Crop the middle 1/factor of the frame — what a zoom-in would have shown."""
    h, w = gray.shape
    ch, cw = int(h / factor), int(w / factor)
    top, left = (h - ch) // 2, (w - cw) // 2
    return gray[top:top + ch, left:left + cw]


def _resize_to(gray, shape):
    """Nearest-neighbour resize; adequate for correlation and dependency-free."""
    h, w = shape
    ys = (np.linspace(0, gray.shape[0] - 1, h)).astype(int)
    xs = (np.linspace(0, gray.shape[1] - 1, w)).astype(int)
    return gray[ys][:, xs]


def _correlate(a, b):
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / denom) if denom else 0.0


def scale_jump_stats(before_url, after_url, max_side=200):
    """Compare the last frame of one shot with the first frame of the next."""
    a = load_gray(before_url, max_side=max_side)
    b = load_gray(after_url, max_side=max_side)
    b = _resize_to(b, a.shape)

    base = _correlate(a, b)                       # no scale change
    best_in, best_in_s = base, 1.0
    for s in SCALES:                               # B is a zoom-IN of A
        cropped = _resize_to(_center_crop(a, s), a.shape)
        score = _correlate(cropped, b)
        if score > best_in:
            best_in, best_in_s = score, s
    best_out, best_out_s = base, 1.0
    for s in SCALES:                               # B is a zoom-OUT (A is the crop of B)
        cropped = _resize_to(_center_crop(b, s), a.shape)
        score = _correlate(a, cropped)
        if score > best_out:
            best_out, best_out_s = score, s

    zoom_in = best_in >= best_out
    best, scale = (best_in, best_in_s) if zoom_in else (best_out, best_out_s)
    return {
        "usable": True,
        "base_correlation": round(base, 3),
        "best_correlation": round(best, 3),
        "gain": round(best - base, 3),
        "scale": scale,
        "direction": "in" if zoom_in else "out",
    }


def scale_jump_plausible(stats):
    return (stats.get("usable")
            and stats["scale"] > 1.0
            and stats["best_correlation"] >= MIN_CORRELATION
            and stats["gain"] >= MIN_GAIN)
