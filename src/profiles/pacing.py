"""Pacing metrics from shot boundaries — the "how it's cut" half of indexing.

Everything here comes from the shot timestamps we already paid for during scene
extraction, so it costs nothing per video and works even where VLM detection is
weak. Shot boundaries ARE the cuts, so cut frequency, cut-length distribution and
rhythm fall straight out of them.

On beat sync: we do not have the audio, so we never claim "cuts on the beat".
Instead we measure how *regular* the cutting is (a low coefficient of variation on
cut intervals, plus a dominant interval that repeats) and call that rhythmic
cutting, which is an honest description of what the timestamps can support.
"""

import statistics

RHYTHMIC_CV_MAX = 0.55       # cut intervals this consistent read as deliberately rhythmic
MIN_CUTS_FOR_RHYTHM = 8
FAST_CUT_S = 1.2             # a cut length at or under this is "fast"


def cut_lengths(shots):
    """Shot durations in order. `shots` = rows with start_s/end_s, sorted by start."""
    return [round(s["end_s"] - s["start_s"], 3) for s in shots]


def histogram(lengths, edges=(0.5, 1, 2, 4, 8)):
    buckets = {f"<{edges[0]}s": 0}
    for lo, hi in zip(edges, edges[1:]):
        buckets[f"{lo}-{hi}s"] = 0
    buckets[f">{edges[-1]}s"] = 0
    for v in lengths:
        if v < edges[0]:
            buckets[f"<{edges[0]}s"] += 1
        elif v >= edges[-1]:
            buckets[f">{edges[-1]}s"] += 1
        else:
            for lo, hi in zip(edges, edges[1:]):
                if lo <= v < hi:
                    buckets[f"{lo}-{hi}s"] += 1
                    break
    return buckets


def rhythm(lengths):
    """How metronomic the cutting is, from interval consistency alone."""
    usable = [v for v in lengths if v > 0]
    if len(usable) < MIN_CUTS_FOR_RHYTHM:
        return {"rhythmic": False, "reason": "too few cuts", "cv": None, "dominant_interval_s": None}
    mean = statistics.fmean(usable)
    cv = statistics.pstdev(usable) / mean if mean else None
    # dominant interval = most common cut length once quantised to quarter-seconds
    quantised = [round(v * 4) / 4 for v in usable]
    dominant = statistics.mode(quantised)
    share = quantised.count(dominant) / len(quantised)
    return {
        "rhythmic": bool(cv is not None and cv <= RHYTHMIC_CV_MAX and share >= 0.25),
        "cv": round(cv, 3) if cv is not None else None,
        "dominant_interval_s": dominant,
        "dominant_share": round(share, 3),
    }


def pacing_curve(shots, buckets=12):
    """Cuts per 10s across the video, so a reader can see where it accelerates."""
    if not shots:
        return []
    duration = max(s["end_s"] for s in shots)
    if duration <= 0:
        return []
    width = duration / buckets
    curve = [0] * buckets
    for s in shots:
        idx = min(buckets - 1, int(s["start_s"] / width))
        curve[idx] += 1
    return [round(c / width * 10, 2) for c in curve]


def summarise(shots):
    lengths = cut_lengths(shots)
    if not lengths:
        return None
    duration = max(s["end_s"] for s in shots)
    fast = sum(1 for v in lengths if v <= FAST_CUT_S)
    return {
        "cuts": len(lengths),
        "duration_s": round(duration, 2),
        "cuts_per_minute": round(len(lengths) / (duration / 60), 2) if duration else None,
        "avg_cut_length_s": round(statistics.fmean(lengths), 2),
        "median_cut_length_s": round(statistics.median(lengths), 2),
        "shortest_cut_s": min(lengths),
        "longest_cut_s": max(lengths),
        "fast_cut_share": round(fast / len(lengths), 3),
        "cut_length_histogram": histogram(lengths),
        "rhythm": rhythm(lengths),
        "pacing_curve_cuts_per_10s": pacing_curve(shots),
    }
