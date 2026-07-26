"""Estimate per-technique precision with an independent second opinion.

Real ground truth needs a human, but an unaudited 582 detections is worse than an
estimate. This samples detections per technique and re-judges each with a *different,
stronger* model tier and an adversarial prompt that must argue the label is wrong.
Agreement is an estimate, not truth — a shared blind spot inflates it — so the output
is labelled as such and the disagreements are printed for eyeballing.

Usage: python scripts/m2_precision.py [--per 12] [--model ultra] [--apply-flags]
"""

import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import LOCK, get_db
from src.detect import pipeline as pl
from src.detect.prompts import SHIPPING_TECHNIQUES, TECHNIQUE_LABELS
from src.videodb_client import get_collection

WORKERS = 12

DEFINITIONS = {
    "whip_pan": "the whole frame is smeared by fast camera motion at the start of the shot,"
                " then settles. A blurred subject over a sharp background does NOT count.",
    "zoom_punch": "an abrupt scale jump at the cut — the same framing suddenly closer or"
                  " wider, often with radial blur.",
    "match_cut": "composition, shape or motion is deliberately carried across a cut that"
                 " changes scene, subject or place.",
    "graphic_match": "composition or shape is deliberately echoed across a cut that stays"
                     " in the same scene. The echo must be a specific named form, not"
                     " simply the same room remaining on screen.",
    "speed_ramp": "playback speed changes inside one continuous shot — frames nearly"
                  " identical in one stretch and far apart in another.",
    "luma_fade": "the shot begins from near-black or near-white, emerging out of a dip.",
}

VERIFY_PROMPT = """You are auditing an automated edit-detection system. Argue against it.

It claims these frames show: {label} — defined as {definition}

Your job is to REFUTE that claim if it is refutable. Look at what the frames actually
show. If the evidence for the claim is not clearly present, say it is wrong. Only
confirm when the claim is plainly supported.

Respond ONLY with JSON:
{{"verdict": "<confirmed|refuted|uncertain>", "confidence": <0.0-1.0>, "why": "<one short sentence>"}}"""


def main(per_technique=12, model="ultra", apply_flags=False):
    db = get_db()
    coll = get_collection()

    sampled = []
    for tech in SHIPPING_TECHNIQUES:
        rows = db.execute(
            "SELECT d.id, d.videodb_id, d.technique, d.confidence, d.cut_time_s,"
            " d.window_start_s, d.window_end_s, v.title, v.account"
            " FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
            " WHERE d.technique=? ORDER BY d.id * 7919 % 1000 LIMIT ?",   # spread, not top-N
            [tech, per_technique]).fetchall()
        sampled.extend(rows)
    print(f"auditing {len(sampled)} detections with model={model}\n")

    scenes_cache = {}

    def audit(row):
        key = (row["account"] or "primary", row["videodb_id"])
        try:
            if key not in scenes_cache:
                video = get_collection(account=key[0]).get_video(row["videodb_id"])
                scenes_cache[key] = (video, pl.extract_shots(video).scenes)
            _video, scenes = scenes_cache[key]
            scene = min(scenes, key=lambda s: abs(s.start - row["cut_time_s"]))
            raw = scene.describe(
                prompt=VERIFY_PROMPT.format(label=row["technique"],
                                            definition=DEFINITIONS[row["technique"]]),
                model_name=model)
            return row, pl.parse_json_reply(raw or "")
        except Exception as e:
            return row, {"verdict": "error", "why": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(audit, sampled))

    stats = defaultdict(lambda: {"confirmed": 0, "refuted": 0, "uncertain": 0, "error": 0})
    refuted = []
    for row, verdict in results:
        v = verdict.get("verdict", "error")
        v = v if v in ("confirmed", "refuted", "uncertain") else "error"
        stats[row["technique"]][v] += 1
        if v == "refuted":
            refuted.append((row, verdict))

    print(f"{'technique':15s} {'n':>3s} {'confirmed':>10s} {'refuted':>8s} {'unsure':>7s} {'est. precision':>15s}")
    overall = {"c": 0, "r": 0}
    for tech in SHIPPING_TECHNIQUES:
        s = stats[tech]
        judged = s["confirmed"] + s["refuted"]
        n = judged + s["uncertain"] + s["error"]
        if not n:
            continue
        overall["c"] += s["confirmed"]
        overall["r"] += s["refuted"]
        est = f"{s['confirmed'] / judged:.0%}" if judged else "—"
        print(f"{TECHNIQUE_LABELS[tech]:15s} {n:3d} {s['confirmed']:10d} {s['refuted']:8d}"
              f" {s['uncertain']:7d} {est:>15s}")
    judged = overall["c"] + overall["r"]
    if judged:
        print(f"\noverall estimated precision: {overall['c'] / judged:.0%}"
              f" ({overall['c']} confirmed / {judged} judged)")
    print("This is second-model agreement, not human ground truth.")

    if refuted:
        print(f"\n{len(refuted)} refuted — worth eyeballing:")
        for row, verdict in refuted[:12]:
            print(f"  #{row['id']:5d} {row['technique']:13s} @{row['cut_time_s']:7.2f}s "
                  f"conf={row['confidence']}  {(row['title'] or '')[:22]:22s} {str(verdict.get('why'))[:60]}")

    if apply_flags and refuted:
        with LOCK:
            db.executemany(
                "UPDATE detections SET evidence = '[audit:refuted] ' || COALESCE(evidence,'')"
                " WHERE id=?", [(row["id"],) for row, _ in refuted])
            db.commit()
        print(f"\nflagged {len(refuted)} detections in the catalog")


if __name__ == "__main__":
    args = sys.argv[1:]
    per = int(args[args.index("--per") + 1]) if "--per" in args else 12
    mdl = args[args.index("--model") + 1] if "--model" in args else "ultra"
    main(per, mdl, "--apply-flags" in args)
