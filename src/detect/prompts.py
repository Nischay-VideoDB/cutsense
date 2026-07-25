"""Technique classification prompts. One structured prompt, versioned.

M0 finding: transition artifacts (whip blur, fade black, zoom smear) land in the
FIRST frames of the shot that follows the cut, so we classify shot-start windows.
"""

PROMPT_VERSION = "v2"

TECHNIQUES = ["whip_pan", "zoom_punch", "luma_fade", "match_cut", "speed_ramp", "hard_cut", "unclear"]

# Match cut: needs the cut PAIR — last frame(s) of shot A + first frame(s) of shot B.
# We build a synthetic boundary Scene with frames from both sides and ask about continuity.
BOUNDARY_PAIR_PROMPT = """You are analyzing frames spanning ONE cut in an edited video.
The first frame(s) are the END of the outgoing shot (before the cut).
The last frame(s) are the START of the incoming shot (after the cut).

Classify the cut:
- match_cut: the two shots show DIFFERENT scenes/subjects/locations, but the composition \
deliberately matches across the cut — same shape, silhouette, framing, screen position, or \
motion continues across the cut (e.g. a spinning bone to a spinning spaceship, a round clock \
to a round wheel, a person jumping in one place landing in another).
- plain_cut: composition does not deliberately carry over, or it is the same scene continuing \
(a normal cut within the same location/subject is NOT a match cut).
- unclear: cannot tell.

Rules:
- match_cut requires BOTH different content AND matched composition/motion. Be strict.
- Same person/place before and after = plain_cut, even if framing is similar.

Respond ONLY with JSON, no prose:
{"label": "<match_cut|plain_cut|unclear>", "confidence": <0.0-1.0>, "evidence": "<one short sentence>"}"""

# Speed ramp: within-shot signal — sampled frames of one shot at even spacing.
SPEED_RAMP_PROMPT = """You are analyzing frames sampled evenly across ONE continuous shot \
(no cuts inside it) from an edited video.

Does this shot contain a SPEED RAMP — footage abruptly changing playback speed (slow-motion \
that snaps to fast motion or vice versa)? Visible signs across the frame sequence:
- some consecutive frames are nearly identical (slow-mo section) while others jump far apart \
(sped-up section) within the same continuous action
- motion blur amount changes abruptly between frames of the same moving subject
- a subject's motion arc is unevenly spaced: tiny increments, then a huge leap

- speed_ramp: strong signs of the above
- constant_speed: motion spacing looks uniform
- unclear: not enough motion to judge

Respond ONLY with JSON, no prose:
{"label": "<speed_ramp|constant_speed|unclear>", "confidence": <0.0-1.0>, "evidence": "<one short sentence>"}"""

SHOT_START_PROMPT = """You are analyzing frames from ONE shot of an edited video to detect editing techniques.
The frames are sampled in time order. The first frame is the moment right after a cut.

Classify what happens at the START of this shot. Choose exactly one label:

- whip_pan: the first frame(s) show strong directional motion blur smearing the whole image \
(horizontal or vertical streaks across everything), then later frames settle into a sharp image. \
The blur must affect the entire frame, not just a moving subject.
- zoom_punch: an abrupt zoom-in or zoom-out right at the shot start — radial blur, or the first \
frames show the same composition at a suddenly different scale, often with slight blur toward edges.
- luma_fade: the first frame(s) are near-black or near-white (a fade or dip), with the image \
emerging from darkness/brightness over the next frames.
- hard_cut: the shot starts clean and sharp. No transition artifact.
- unclear: frames are ambiguous or contradictory.

Rules:
- A blurry moving SUBJECT on a sharp background is NOT a whip_pan.
- Judge only the start of the shot; ignore what happens later.
- Be conservative: prefer hard_cut over a technique unless the artifact is obvious.

Respond ONLY with JSON, no prose:
{"label": "<one label>", "confidence": <0.0-1.0>, "evidence": "<one short sentence>"}"""
