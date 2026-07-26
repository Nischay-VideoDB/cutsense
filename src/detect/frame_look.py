"""Pixel signals for the within-shot looks: split screen, shake, glitch.

Each has a cheap deterministic tell, so the model is only asked about candidates —
the same two-stage shape that made whip pan precise and speed ramp possible.

- split screen: a straight divider produces a persistent, unusually strong edge along
  one whole column or row, in the same place across frames.
- shake: the whole frame displaces between consecutive frames. Distinguished from a
  whip pan by direction changing sign repeatedly rather than smearing one way.
- glitch: rows or blocks disagree with their neighbours far more than in natural
  footage, and the colour channels stop lining up.
"""

import numpy as np

from src.detect.filters import load_gray

SPLIT_MIN_EDGE_RATIO = 4.0    # divider column strength vs the frame's average column
SPLIT_MIN_PERSIST = 0.75      # fraction of frames whose divider sits in the same place
SHAKE_MIN_REVERSALS = 2       # direction sign changes across the window
SHAKE_MIN_DISPLACEMENT = 1.2
GLITCH_MIN_ROW_ANOMALY = 3.5


def _column_energy(gray):
    """Mean vertical-gradient magnitude per column — a hard divider spikes."""
    gx = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    return gx


def _row_energy(gray):
    return np.abs(np.diff(gray, axis=0)).mean(axis=1)


def split_screen_stats(frame_urls, max_side=320):
    cols, rows, positions = [], [], []
    for url in frame_urls:
        gray = load_gray(url, max_side=max_side)
        ce, re_ = _column_energy(gray), _row_energy(gray)
        # ignore the outer 12%: real dividers sit inside the frame, borders always spike
        pad_c, pad_r = int(len(ce) * 0.12), int(len(re_) * 0.12)
        inner_c, inner_r = ce[pad_c:-pad_c or None], re_[pad_r:-pad_r or None]
        if not len(inner_c) or not len(inner_r):
            continue
        c_ratio = inner_c.max() / max(inner_c.mean(), 1e-6)
        r_ratio = inner_r.max() / max(inner_r.mean(), 1e-6)
        cols.append(c_ratio)
        rows.append(r_ratio)
        vertical = c_ratio >= r_ratio
        idx = int(inner_c.argmax() if vertical else inner_r.argmax())
        span = len(inner_c) if vertical else len(inner_r)
        positions.append(("v" if vertical else "h", round(idx / span, 2)))

    if not cols:
        return {"usable": False}
    best_ratio = max(max(cols), max(rows))
    # persistence: same orientation and roughly the same position across frames
    if positions:
        common = max(set((o, round(p, 1)) for o, p in positions),
                     key=lambda k: sum(1 for o, p in positions if (o, round(p, 1)) == k))
        persist = sum(1 for o, p in positions if (o, round(p, 1)) == common) / len(positions)
    else:
        common, persist = None, 0.0
    return {"usable": True, "edge_ratio": round(best_ratio, 2),
            "persistence": round(persist, 2), "divider": common}


def split_screen_plausible(stats):
    return (stats.get("usable")
            and stats["edge_ratio"] >= SPLIT_MIN_EDGE_RATIO
            and stats["persistence"] >= SPLIT_MIN_PERSIST)


def shake_stats(frame_urls, max_side=240):
    """Track coarse frame displacement by comparing row/column profiles."""
    profiles = []
    for url in frame_urls:
        gray = load_gray(url, max_side=max_side)
        profiles.append((gray.mean(axis=0), gray.mean(axis=1)))
    if len(profiles) < 3:
        return {"usable": False}

    def shift(a, b, limit=6):
        """Best integer offset aligning two 1-D profiles."""
        best, best_err = 0, None
        for off in range(-limit, limit + 1):
            if off < 0:
                x, y = a[-off:], b[:len(b) + off]
            elif off > 0:
                x, y = a[:len(a) - off], b[off:]
            else:
                x, y = a, b
            n = min(len(x), len(y))
            if n < 8:
                continue
            err = float(np.abs(x[:n] - y[:n]).mean())
            if best_err is None or err < best_err:
                best, best_err = off, err
        return best

    dx = [shift(profiles[i][0], profiles[i + 1][0]) for i in range(len(profiles) - 1)]
    dy = [shift(profiles[i][1], profiles[i + 1][1]) for i in range(len(profiles) - 1)]
    def reversals(seq):
        signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in seq]
        nz = [s for s in signs if s]
        return sum(1 for a, b in zip(nz, nz[1:]) if a != b)
    displacement = float(np.mean([abs(a) + abs(b) for a, b in zip(dx, dy)]))
    return {"usable": True, "dx": dx, "dy": dy,
            "reversals": max(reversals(dx), reversals(dy)),
            "displacement": round(displacement, 2)}


def shake_plausible(stats):
    return (stats.get("usable")
            and stats["displacement"] >= SHAKE_MIN_DISPLACEMENT
            and stats["reversals"] >= SHAKE_MIN_REVERSALS)


def glitch_stats(frame_urls, max_side=320):
    """Row-to-row disagreement: tearing and block corruption spike it.

    Letterbox bars produce an enormous single row jump in almost every video, so the
    outer rows are cropped away and the measure counts *how many* rows disagree
    rather than the single worst one — corruption tears several rows, a black bar one.
    """
    worst_anomaly, worst_count = 0.0, 0
    for url in frame_urls:
        gray = load_gray(url, max_side=max_side)
        pad = max(1, int(gray.shape[0] * 0.14))
        inner = gray[pad:-pad or None, :]
        if inner.shape[0] < 8:
            continue
        row_means = inner.mean(axis=1)
        diffs = np.abs(np.diff(row_means))
        if not len(diffs):
            continue
        med = float(np.median(diffs)) or 1e-6
        anomaly = float(diffs.max() / med)
        torn = int((diffs > med * 8).sum())
        worst_anomaly = max(worst_anomaly, anomaly)
        worst_count = max(worst_count, torn)
    return {"usable": worst_anomaly > 0, "row_anomaly": round(worst_anomaly, 2),
            "torn_rows": worst_count}


def glitch_plausible(stats):
    return stats.get("usable") and stats["row_anomaly"] >= GLITCH_MIN_ROW_ANOMALY
