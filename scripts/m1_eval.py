"""Evaluate detections vs weak labels (technique_hint) and hand labels.

Weak eval (per video): does the video contain >=1 accepted detection for each
technique in its technique_hint? -> library-level recall proxy.
Strong eval (per cut, when `labels` rows exist): detection within +/-1.5s of a
labeled cut_time counts as a hit -> precision/recall.

Usage: python scripts/m1_eval.py
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db

TOL = 1.5
HINT_MAP = {"whip-pan": "whip_pan", "match-cut": "match_cut", "speed-ramping": "speed_ramp"}
CONF = {"whip_pan": 0.85, "zoom_punch": 0.85, "luma_fade": 0.9, "match_cut": 0.85,
        "graphic_match": 0.85, "speed_ramp": 0.85}
# eyecannndy's "match cut" category mixes both; either satisfies the weak label
HINT_ALSO_SATISFIED_BY = {"match_cut": {"graphic_match"}}


def main():
    db = get_db()

    print("=== Weak eval (video-level: hint technique detected anywhere?)")
    print("    HIT = detected · miss = detector ran, found nothing · n/a = detector not run yet")
    rows = db.execute("SELECT videodb_id, title, technique_hint FROM videos WHERE technique_hint IS NOT NULL")
    for r in rows:
        hints = [HINT_MAP.get(h, h) for h in r["technique_hint"].split(",")]
        dets = list(db.execute(
            "SELECT technique, confidence FROM detections WHERE videodb_id=?", [r["videodb_id"]]))
        found = {d["technique"] for d in dets
                 if d["technique"] in CONF and d["confidence"] >= CONF[d["technique"]]}
        # a detector "ran" if it stored any row for that technique, accepted or rejected
        ran = {t.replace("rejected:", "") for t in (d["technique"] for d in dets)}
        marks = []
        for h in hints:
            if found & ({h} | HINT_ALSO_SATISFIED_BY.get(h, set())):
                marks.append(f"{h}:HIT")
            elif h in ran or (h == "whip_pan" and "hard_cut" in ran):
                marks.append(f"{h}:miss")
            else:
                marks.append(f"{h}:n/a")
        print(f"  {r['title'][:45]:45s} {' '.join(marks)}")

    print("\n=== Strong eval (cut-level vs hand labels)")
    labels = list(db.execute("SELECT * FROM labels"))
    if not labels:
        print("  no hand labels yet — add rows to `labels` table")
        return
    per_tech = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0})
    matched_det_ids = set()
    for lb in labels:
        dets = list(db.execute(
            "SELECT id FROM detections WHERE videodb_id=? AND technique=? AND confidence>=?"
            " AND ABS(cut_time_s - ?) <= ?",
            [lb["videodb_id"], lb["technique"], CONF.get(lb["technique"], 0.85), lb["cut_time_s"], TOL]))
        if dets:
            per_tech[lb["technique"]]["tp"] += 1
            matched_det_ids.update(d["id"] for d in dets)
        else:
            per_tech[lb["technique"]]["fn"] += 1
    for t, conf in CONF.items():
        vids = {lb["videodb_id"] for lb in labels}
        for vid in vids:  # false positives only counted on hand-labeled videos
            fps = db.execute(
                "SELECT COUNT(*) c FROM detections WHERE videodb_id=? AND technique=? AND confidence>=?"
                " AND id NOT IN (%s)" % (",".join(map(str, matched_det_ids)) or "0"),
                [vid, t, conf]).fetchone()["c"]
            per_tech[t]["fp"] += fps
    for t, m in sorted(per_tech.items()):
        p = m["tp"] / (m["tp"] + m["fp"]) if (m["tp"] + m["fp"]) else 0
        r = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) else 0
        print(f"  {t:12s} tp={m['tp']} fp={m['fp']} fn={m['fn']}  precision={p:.2f} recall={r:.2f}")


if __name__ == "__main__":
    main()
