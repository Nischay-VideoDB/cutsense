"""Re-classify audited detections with the current prompt and score the change.

The audit gave every shot-start detection a verdict, which makes a labelled set:
verified=1 are the ones to keep, verified=0 the ones to drop. Re-running the
classifier over both tells us whether a prompt edit actually helped, instead of
eyeballing a couple of clips and hoping.

Usage: python scripts/m2_eval_prompt.py [--technique zoom_punch] [--sample 40]
"""

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db
from src.detect import pipeline as pl
from src.videodb_client import get_collection

WORKERS = 12


def main(technique="zoom_punch", sample=40):
    db = get_db()
    keep = db.execute(
        "SELECT d.id, d.videodb_id, d.cut_time_s, v.account FROM detections d"
        " JOIN videos v ON v.videodb_id=d.videodb_id"
        " WHERE d.technique=? AND d.verified=1 ORDER BY d.id * 7919 % 1000 LIMIT ?",
        [technique, sample]).fetchall()
    drop = db.execute(
        "SELECT d.id, d.videodb_id, d.cut_time_s, v.account FROM detections d"
        " JOIN videos v ON v.videodb_id=d.videodb_id"
        " WHERE d.technique=? AND d.verified=0 ORDER BY d.id * 7919 % 1000 LIMIT ?",
        [technique, sample]).fetchall()
    print(f"labelled set for {technique}: {len(keep)} should stay, {len(drop)} should go\n")

    cache = {}

    def classify(row):
        key = (row["account"] or "primary", row["videodb_id"])
        try:
            if key not in cache:
                video = get_collection(account=key[0]).get_video(row["videodb_id"])
                cache[key] = pl.extract_shots(video).scenes
            scenes = cache[key]
            scene = min(scenes, key=lambda s: abs(s.start - row["cut_time_s"]))
            model = pl.resolve_model(scene)
            raw = scene.describe(prompt=pl.SHOT_START_PROMPT, model_name=model)
            return pl.parse_json_reply(raw or "")
        except Exception as e:
            return {"label": "error", "evidence": str(e)[:80]}

    def run(rows, name):
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(classify, rows))
        labels = Counter(r.get("label") for r in results)
        still = sum(1 for r in results
                    if r.get("label") == technique
                    and float(r.get("confidence") or 0) >= pl.CONF_THRESHOLD.get(technique, 0.85))
        print(f"{name}: still called {technique} -> {still}/{len(rows)}   {dict(labels)}")
        return still, len(rows)

    kept, n_keep = run(keep, "true positives ")
    wrong, n_drop = run(drop, "false positives")

    print()
    if n_keep:
        print(f"recall on known-good:      {kept}/{n_keep} = {kept / n_keep:.0%}")
    if n_drop:
        print(f"false positives surviving: {wrong}/{n_drop} = {wrong / n_drop:.0%}"
              f"   (was 100% by construction)")
    if n_keep and n_drop:
        est = kept / (kept + wrong) if (kept + wrong) else 0
        print(f"implied precision on this mix: {est:.0%} (was {n_keep / (n_keep + n_drop):.0%})")


if __name__ == "__main__":
    args = sys.argv[1:]
    tech = args[args.index("--technique") + 1] if "--technique" in args else "zoom_punch"
    n = int(args[args.index("--sample") + 1]) if "--sample" in args else 40
    main(tech, n)
