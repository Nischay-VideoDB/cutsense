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

# v3: the v2 judge accepted "similar composition" even when the shots were the same
# scene continuing (26 of 69 cuts on one teaser). Forcing it to commit to the two
# intermediate facts first, and deriving the label in code, fixes that.
MATCH_JUDGE_PROMPT = """Two frames sit on either side of a CUT in an edited video.

FRAME A (end of outgoing shot): {desc_a}

FRAME B (start of incoming shot): {desc_b}

Answer two independent questions, then nothing else.

1. same_context: Do both frames show the SAME location/scene/set, or the same subject
continuing the same action? A cut between two angles of one ongoing scene = true.
A cut to a genuinely different place, subject, time, or subject matter = false.
When the descriptions plausibly describe one continuous scene, answer true.

2. composition_match: Is a specific concrete visual element deliberately carried across
the cut — the same dominant shape or silhouette, the same screen position of the main
form, the same distinctive framing geometry, or a motion direction that continues?
Generic similarity ("both are dark", "both are centered", "both are close-ups") is NOT
a composition match. Answer false unless you can name the specific matched element.

Respond ONLY with JSON:
{{"same_context": <true|false>, "composition_match": <true|false>,
 "matched_element": "<the specific element, or empty>", "confidence": <0.0-1.0>,
 "evidence": "<one short sentence>"}}"""


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


def match_cut_label(result):
    """Derive the label in code from the judge's two committed facts.

    Two distinct techniques fall out of the same pair of booleans:
      match_cut     - matched composition ACROSS a change of scene/subject (the classic)
      graphic_match - matched composition while staying in the same scene, which is
                      what a lot of curated "match cut" examples actually are
    """
    if result.get("same_context") is None or result.get("composition_match") is None:
        return result.get("label", "unclear")
    if not result["composition_match"]:
        return "plain_cut"
    return "graphic_match" if result["same_context"] else "match_cut"


def accepted_boundary(result):
    """True when the derived label is a technique we ship, at sufficient confidence."""
    label = match_cut_label(result)
    return (label in ("match_cut", "graphic_match")
            and float(result.get("confidence") or 0) >= MATCH_CUT_CONF
            and bool(str(result.get("matched_element") or "").strip()))


def accepted_match_cut(result):
    return accepted_boundary(result) and match_cut_label(result) == "match_cut"


def accepted_speed_ramp(result):
    return result.get("label") == "speed_ramp" and float(result.get("confidence") or 0) >= SPEED_RAMP_CONF
