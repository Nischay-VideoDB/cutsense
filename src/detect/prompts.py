"""Technique classification prompts. One structured prompt, versioned.

M0 finding: transition artifacts (whip blur, fade black, zoom smear) land in the
FIRST frames of the shot that follows the cut, so we classify shot-start windows.
"""

PROMPT_VERSION = "v1"

TECHNIQUES = ["whip_pan", "zoom_punch", "luma_fade", "hard_cut", "unclear"]

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
