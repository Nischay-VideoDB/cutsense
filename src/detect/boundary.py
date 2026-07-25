"""Boundary-pair detection (match cuts) and within-shot detection (speed ramps).

Match cut mechanics (constraint discovered 2026-07-26): Scene.describe() requires a
server-side scene id, so synthetic cross-boundary Scenes can't be described directly.
Fallback pipeline per cut:
  1. Frame.describe() on last frame of shot A and first sharp frame of shot B
     (frames from extract_scenes have server ids) with a composition-focused prompt
  2. collection.generate_text() judges match-cut from the two descriptions

Speed ramp: within-shot — Scene.describe() works normally (scenes have server ids).
"""

import json
import re

from src.detect.pipeline import parse_json_reply
from src.detect.prompts import SPEED_RAMP_PROMPT

MATCH_CUT_CONF = 0.85
SPEED_RAMP_CONF = 0.85
MIN_SHOT_DUR = 0.15

FRAME_COMPO_PROMPT = """Describe this single video frame for edit analysis, in <=60 words, covering:
1) subject(s) and setting, 2) composition: dominant shapes, screen position of the subject,
framing (close/medium/wide), camera angle, 3) any dominant motion direction or blur.
Plain prose, no preamble."""

MATCH_JUDGE_PROMPT = """Two consecutive frames sit on either side of a CUT in an edited video.

FRAME A (end of outgoing shot): {desc_a}

FRAME B (start of incoming shot): {desc_b}

A match cut means: DIFFERENT scene/subject/location, but deliberately matched composition
(same dominant shape, silhouette, screen position, framing, or continued motion direction).
Same scene/subject continuing = plain_cut. Be strict.

Respond ONLY with JSON: {{"label": "<match_cut|plain_cut|unclear>", "confidence": <0.0-1.0>, "evidence": "<one short sentence>"}}"""


def _first_sharp_frame(scene):
    # first frame may be transition blur (whip/fade); prefer a later frame for composition
    return scene.frames[-1] if len(scene.frames) > 1 else scene.frames[0]


def classify_boundaries(coll, scenes, frame_cache=None):
    """Yield (shot_idx, cut_time, result) per cut. frame_cache: dict frame_id -> description."""
    frame_cache = frame_cache if frame_cache is not None else {}

    def describe_frame(frame):
        if frame.id not in frame_cache:
            frame_cache[frame.id] = frame.describe(prompt=FRAME_COMPO_PROMPT)
        return frame_cache[frame.id]

    for i in range(1, len(scenes)):
        a, b = scenes[i - 1], scenes[i]
        if (a.end - a.start) < MIN_SHOT_DUR or (b.end - b.start) < MIN_SHOT_DUR:
            continue
        desc_a = describe_frame(a.frames[-1])
        desc_b = describe_frame(_first_sharp_frame(b))
        raw = coll.generate_text(
            prompt=MATCH_JUDGE_PROMPT.format(desc_a=desc_a, desc_b=desc_b),
            model_name="basic", response_type="json")
        if isinstance(raw, dict):
            result = raw.get("output", raw)  # generate_text(json) wraps payload in "output"
        else:
            result = parse_json_reply(str(raw))
        yield i, b.start, result


def classify_speed_ramps(scenes, min_dur=1.0):
    """Within-shot speed-ramp check; skip very short shots (no room for a ramp)."""
    for i, scene in enumerate(scenes):
        if (scene.end - scene.start) < min_dur:
            continue
        raw = scene.describe(prompt=SPEED_RAMP_PROMPT)
        result = parse_json_reply(raw or "")
        yield i, scene.start, result


def accepted_match_cut(result):
    return result.get("label") == "match_cut" and float(result.get("confidence") or 0) >= MATCH_CUT_CONF


def accepted_speed_ramp(result):
    return result.get("label") == "speed_ramp" and float(result.get("confidence") or 0) >= SPEED_RAMP_CONF
