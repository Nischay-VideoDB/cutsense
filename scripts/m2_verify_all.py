"""Audit every detection with an independent model and record the verdict.

Rationale: a sampled audit put estimated precision at ~15%, and the auditor itself
scored 8/9 against visually verified controls, so the low number is credible rather
than an artefact. A confident label from one classifier is not evidence; agreement
between two is at least a filter. `detections.verified` becomes the gate the UI
trusts (1 confirmed, 0 refuted, NULL not yet audited).

Runs newest-first so a partial pass still improves what people see, and tolerates the
audit tier's budget dying mid-run — whatever was verified is kept.

Usage: python scripts/m2_verify_all.py [--model ultra] [--limit N] [--technique whip_pan]
"""

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import LOCK, get_db
from src.detect import pipeline as pl
from src.detect.prompts import SHIPPING_TECHNIQUES
from src.videodb_client import get_collection

WORKERS = 12

DEFINITIONS = {
    "whip_pan": "the whole frame is smeared by fast camera motion at the start of the shot,"
                " then settles. A blurred subject over a sharp background does NOT count.",
    "zoom_punch": "an abrupt scale jump at the cut — the same framing suddenly closer or"
                  " wider, often with radial blur.",
    "match_cut": "composition, shape or motion deliberately carried across a cut that"
                 " changes scene, subject or place.",
    "graphic_match": "a specific named shape or form deliberately echoed across a cut that"
                     " stays in the same scene. The same room remaining on screen is not enough.",
    "speed_ramp": "playback speed changes inside one continuous shot — frames nearly"
                  " identical in one stretch and far apart in another.",
    "luma_fade": "the shot begins from near-black or near-white, emerging out of a dip.",
}

# Neutral wording: measured to agree exactly with an adversarial version on controls,
# without the risk of a refute-by-default bias.
PROMPT = """Judge one claim about these frames, which come from the start of a shot.

Claim: this is a {label} — {definition}

Decide what the frames actually show, without favouring either answer.

Respond ONLY with JSON:
{{"verdict": "<confirmed|refuted|uncertain>", "confidence": <0.0-1.0>, "why": "<one short sentence>"}}"""


def main(model="ultra", limit=None, technique=None):
    db = get_db()
    where = ["d.verified IS NULL",
             f"d.technique IN ({','.join('?' * len(SHIPPING_TECHNIQUES))})"]
    params = list(SHIPPING_TECHNIQUES)
    if technique:
        where.append("d.technique = ?")
        params.append(technique)
    sql = ("SELECT d.id, d.videodb_id, d.technique, d.confidence, d.cut_time_s, v.account"
           " FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
           f" WHERE {' AND '.join(where)} ORDER BY d.id DESC")
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.execute(sql, params).fetchall()
    print(f"{len(rows)} detections to audit with model={model}")

    cache = {}
    tally = Counter()

    def audit(row):
        key = (row["account"] or "primary", row["videodb_id"])
        try:
            if key not in cache:
                video = get_collection(account=key[0]).get_video(row["videodb_id"])
                cache[key] = pl.extract_shots(video).scenes
            scenes = cache[key]
            scene = min(scenes, key=lambda s: abs(s.start - row["cut_time_s"]))
            raw = scene.describe(
                prompt=PROMPT.format(label=row["technique"],
                                     definition=DEFINITIONS[row["technique"]]),
                model_name=model)
            return row, pl.parse_json_reply(raw or "")
        except Exception as e:
            return row, {"verdict": "error", "why": f"{type(e).__name__}: {str(e)[:90]}"}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for row, out in pool.map(audit, rows):
            verdict = out.get("verdict")
            tally[verdict or "error"] += 1
            if verdict in ("confirmed", "refuted"):
                with LOCK:
                    db.execute("UPDATE detections SET verified=?, verify_note=? WHERE id=?",
                               [1 if verdict == "confirmed" else 0,
                                f"{verdict}: {str(out.get('why'))[:160]}", row["id"]])
                    db.commit()
            if sum(tally.values()) % 25 == 0:
                print(f"  {sum(tally.values())}/{len(rows)} {dict(tally)}")

    print(f"\nfinal: {dict(tally)}")
    kept = db.execute("SELECT COUNT(*) c FROM detections WHERE verified=1").fetchone()["c"]
    refuted = db.execute("SELECT COUNT(*) c FROM detections WHERE verified=0").fetchone()["c"]
    print(f"catalog now: {kept} verified, {refuted} refuted")
    for r in db.execute(
            "SELECT technique, SUM(verified=1) ok, SUM(verified=0) no FROM detections"
            f" WHERE technique IN ({','.join('?' * len(SHIPPING_TECHNIQUES))})"
            " GROUP BY technique", SHIPPING_TECHNIQUES):
        total = (r["ok"] or 0) + (r["no"] or 0)
        if total:
            print(f"  {r['technique']:14s} {r['ok']:4d} kept / {total:4d} audited"
                  f"  ({(r['ok'] or 0) / total:.0%})")


if __name__ == "__main__":
    args = sys.argv[1:]
    mdl = args[args.index("--model") + 1] if "--model" in args else "ultra"
    lim = args[args.index("--limit") + 1] if "--limit" in args else None
    tech = args[args.index("--technique") + 1] if "--technique" in args else None
    main(mdl, lim, tech)
