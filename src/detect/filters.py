"""Deterministic pixel-stat filters over frame images.

Purpose: gate the VLM. The VLM alone confuses a blurred SUBJECT on a sharp
background with a real whip pan (observed on IKEA ad @6.4s, conf 0.98). A whip
pan blurs the WHOLE frame, including the background at the edges, and the blur
is directional.

Metrics per frame:
- sharpness: variance of a Laplacian-like kernel (higher = sharper)
- border_sharpness: same, over the outer band only (background proxy)
- directionality: ratio of horizontal to vertical gradient energy; a horizontal
  whip smears horizontally, so vertical edges vanish and the ratio departs from 1
- luma: mean brightness (luma_fade check)
"""

import io
import urllib.request

import numpy as np
from PIL import Image

BORDER_FRAC = 0.18          # outer band width as fraction of the shorter side
FADE_MAX_LUMA = 40
FADE_MIN_LUMA = 215

# Calibrated 2026-07-26 on 10 hand-labeled frames: real whip-pan frames measured
# sharpness 30-160, false positives 278-2511. Absolute values are content-dependent,
# so the primary gate is the ratio against a settled frame from the SAME shot.
WHIP_MAX_SHARPNESS = 220     # globally soft frame (whole shot may stay in motion)
WHIP_MIN_SHARP_RATIO = 1.5   # settled_frame_sharpness / first_frame_sharpness


def load_gray(url_or_path, max_side=480):
    if str(url_or_path).startswith("http"):
        with urllib.request.urlopen(url_or_path, timeout=30) as r:
            img = Image.open(io.BytesIO(r.read()))
    else:
        img = Image.open(url_or_path)
    img = img.convert("L")
    if max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return np.asarray(img, dtype=np.float32)


def _laplacian_var(a):
    if a.size == 0:
        return 0.0
    lap = (a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4 * a[1:-1, 1:-1])
    return float(lap.var())


def frame_stats(gray):
    h, w = gray.shape
    band = max(2, int(min(h, w) * BORDER_FRAC))
    border = np.concatenate([
        gray[:band, :].ravel(), gray[-band:, :].ravel(),
        gray[:, :band].ravel(), gray[:, -band:].ravel(),
    ])
    border_img = np.concatenate([gray[:band, :], gray[-band:, :]], axis=0)

    gx = np.abs(np.diff(gray, axis=1)).mean()
    gy = np.abs(np.diff(gray, axis=0)).mean()
    directionality = max(gx, gy) / max(min(gx, gy), 1e-6)

    return {
        "sharpness": _laplacian_var(gray),
        "border_sharpness": _laplacian_var(border_img),
        "directionality": directionality,
        "smear_axis": "horizontal" if gy > gx else "vertical",
        "luma": float(gray.mean()),
        "border_luma": float(border.mean()),
    }


def whip_plausible(first_stats, settled_stats=None) -> bool:
    """A whip pan softens the WHOLE frame at the cut, then settles.

    Two ways to qualify, because some shots never settle (the whole shot is in
    motion, or the footage is dark and soft):
      - the frame sharpens measurably later in the same shot (content-normalized), or
      - the first frame is globally soft in absolute terms.
    This is a permissive gate — the VLM still has to agree. It exists to veto
    sharp frames the VLM wrongly calls whip pans.
    """
    if settled_stats is not None:
        ratio = settled_stats["sharpness"] / max(first_stats["sharpness"], 1e-6)
        if ratio >= WHIP_MIN_SHARP_RATIO:
            return True
    return first_stats["sharpness"] <= WHIP_MAX_SHARPNESS


def shot_whip_stats(scene):
    """Stats for a shot's first frame and its most-settled (sharpest later) frame."""
    first = stats_for(scene.frames[0].url)
    later = [stats_for(f.url) for f in scene.frames[1:]]
    settled = max(later, key=lambda s: s["sharpness"]) if later else None
    return first, settled


def fade_plausible(stats) -> bool:
    return stats["luma"] <= FADE_MAX_LUMA or stats["luma"] >= FADE_MIN_LUMA


def stats_for(url_or_path):
    return frame_stats(load_gray(url_or_path))
