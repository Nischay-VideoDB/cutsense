"""Calibrate the precision auditor before trusting its numbers.

The adversarial audit refuted 85% of detections, which contradicts direct visual
inspection of the same kind of clips. An auditor instructed to "refute if refutable"
can refute everything, so its output is only meaningful if it separates cases we have
already checked by eye.

Controls, all verified visually earlier in development:
  TRUE  — genuine whole-frame whip-pan smear
  FALSE — sharp frames the classifier wrongly called whip pans (these were the ones
          the pixel veto later caught)

Two prompts are compared: the adversarial one used in the audit, and a neutral one.

Usage: python scripts/m2_audit_controls.py
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db
from src.detect import pipeline as pl
from src.videodb_client import get_collection

CLASSROOM = "m-z-019f9a8e-a38d-7f23-b961-8f9c3da96a20"
TUTORIAL = "m-z-019f9a8e-dd77-7510-a4fb-c1c298b656af"
ASD = "m-z-019f9aab-eff6-7ad1-a6a4-e3c6cf179086"

CONTROLS = [
    (CLASSROOM, 1.40, True), (CLASSROOM, 3.56, True),
    (TUTORIAL, 34.00, True), (TUTORIAL, 50.50, True), (TUTORIAL, 97.92, True),
    (ASD, 204.36, True),
    (TUTORIAL, 46.96, False), (ASD, 121.44, False), (CLASSROOM, 2.96, False),
]

DEFINITION = ("the whole frame is smeared by fast camera motion at the start of the shot,"
              " then settles. A blurred subject over a sharp background does NOT count.")

ADVERSARIAL = """You are auditing an automated edit-detection system. Argue against it.

It claims these frames show: whip_pan — defined as {definition}

Your job is to REFUTE that claim if it is refutable. Look at what the frames actually
show. If the evidence for the claim is not clearly present, say it is wrong. Only
confirm when the claim is plainly supported.

Respond ONLY with JSON:
{{"verdict": "<confirmed|refuted|uncertain>", "confidence": <0.0-1.0>, "why": "<one short sentence>"}}"""

NEUTRAL = """Judge one claim about these frames, which come from the start of a shot.

Claim: this is a whip_pan — {definition}

Decide what the frames actually show, without favouring either answer.

Respond ONLY with JSON:
{{"verdict": "<confirmed|refuted|uncertain>", "confidence": <0.0-1.0>, "why": "<one short sentence>"}}"""


def main():
    coll_cache = {}

    def scene_for(video_id, cut_time, account):
        key = (account, video_id)
        if key not in coll_cache:
            video = get_collection(account=account).get_video(video_id)
            coll_cache[key] = (video, pl.extract_shots(video).scenes)
        _v, scenes = coll_cache[key]
        return min(scenes, key=lambda s: abs(s.start - cut_time))

    db = get_db()
    accounts = {r["videodb_id"]: (r["account"] or "primary") for r in
                db.execute("SELECT videodb_id, account FROM videos")}

    def judge(item):
        video_id, cut, truth, prompt_name, prompt = item
        try:
            scene = scene_for(video_id, cut, accounts.get(video_id, "legacy"))
            raw = scene.describe(prompt=prompt.format(definition=DEFINITION), model_name="ultra")
            return item, pl.parse_json_reply(raw or "")
        except Exception as e:
            return item, {"verdict": "error", "why": str(e)[:70]}

    work = [(v, c, t, name, prompt)
            for v, c, t in CONTROLS
            for name, prompt in (("adversarial", ADVERSARIAL), ("neutral", NEUTRAL))]

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(judge, work))

    print(f"{'case':34s} {'truth':6s} {'prompt':12s} {'verdict':10s} why")
    tally = {}
    for (video_id, cut, truth, name, _p), out in results:
        verdict = out.get("verdict", "error")
        label = f"{video_id[-8:]}@{cut}"
        key = (name, truth)
        agree = (verdict == "confirmed") == truth
        tally[key] = tally.get(key, [0, 0])
        tally[key][0] += 1 if agree else 0
        tally[key][1] += 1
        print(f"{label:34s} {str(truth):6s} {name:12s} {verdict:10s} {str(out.get('why'))[:52]}")

    print("\nauditor accuracy against visually verified controls:")
    for name in ("adversarial", "neutral"):
        for truth in (True, False):
            ok, n = tally.get((name, truth), [0, 0])
            kind = "true positives" if truth else "true negatives"
            if n:
                print(f"  {name:12s} {kind:15s} {ok}/{n} correct")


if __name__ == "__main__":
    main()
