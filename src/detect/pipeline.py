"""Detection pipeline: shots -> shot-start VLM classification -> detections.

Validators (M0 findings):
- min shot duration 0.15s (filters end-of-video stubs)
- confidence threshold per technique
- luma_fade at the very last shot of a video is an outro fade, kept but tagged
"""

import json
import re

from videodb import SceneExtractionType

from src.detect.prompts import PROMPT_VERSION, SHOT_START_PROMPT

MIN_SHOT_DUR = 0.15
CONF_THRESHOLD = {"whip_pan": 0.85, "zoom_punch": 0.85, "luma_fade": 0.9}
CONTEXT_S = 1.5  # clip window padding around the cut


def extract_shots(video, threshold=20, frame_count=3):
    return video.extract_scenes(
        extraction_type=SceneExtractionType.shot_based,
        extraction_config={"threshold": threshold, "frame_count": frame_count},
    )


def parse_json_reply(text: str):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"label": "unclear", "confidence": 0.0, "evidence": f"unparseable: {text[:80]}"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"label": "unclear", "confidence": 0.0, "evidence": f"bad json: {text[:80]}"}


def classify_shots(scene_collection, skip_first=True):
    """Yield (shot_idx, scene, result) for technique-positive shots + all classifications."""
    scenes = scene_collection.scenes
    for i, scene in enumerate(scenes):
        if skip_first and i == 0:
            continue  # first shot has no preceding cut
        if scene.end - scene.start < MIN_SHOT_DUR:
            continue
        raw = scene.describe(prompt=SHOT_START_PROMPT)
        result = parse_json_reply(raw or "")
        yield i, scene, result


def is_accepted(result) -> bool:
    label = result.get("label")
    conf = float(result.get("confidence") or 0)
    return label in CONF_THRESHOLD and conf >= CONF_THRESHOLD[label]


def detection_window(scene, video_length):
    cut = scene.start
    return max(0.0, cut - CONTEXT_S), min(float(video_length), cut + CONTEXT_S)


__all__ = [
    "extract_shots", "classify_shots", "is_accepted", "detection_window",
    "PROMPT_VERSION", "MIN_SHOT_DUR", "CONF_THRESHOLD",
]
