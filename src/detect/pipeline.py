"""Detection pipeline: shots -> shot-start VLM classification -> detections.

Validators (M0 findings):
- min shot duration 0.15s (filters end-of-video stubs)
- confidence threshold per technique
- luma_fade at the very last shot of a video is an outro fade, kept but tagged
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor

from videodb import SceneExtractionType
from videodb.exceptions import InvalidRequestError

from src.detect.prompts import PROMPT_VERSION, SHOT_START_PROMPT

MIN_SHOT_DUR = 0.15
WORKERS = 8  # serial describe was ~4.6s/shot; 170-shot video took ~13 min

# Model tiers are budgeted separately, and a spent tier fails every call with
# "You have reached the Hackathon budget for this model tier". That once turned
# into 87 shots of silent "unclear", so the tier is resolved once against a live
# call and remembered, falling forward through the chain when one is exhausted.
MODEL_CHAIN = ("basic", "pro", "ultra")
BUDGET_MARKERS = ("budget", "not supported")
_resolved_model = {}


def resolve_model(scene, chain=MODEL_CHAIN, account="primary"):
    """Return the first tier that answers, or None if the default works."""
    if account in _resolved_model:
        return _resolved_model[account]
    for model in chain:
        try:
            scene.describe(prompt="Reply with only the word OK.", model_name=model)
            _resolved_model[account] = model
            return model
        except Exception as e:
            if not any(m in str(e).lower() for m in BUDGET_MARKERS):
                raise
    raise RuntimeError("no LLM tier available: every tier in the chain is exhausted")


def model_for(account="primary"):
    return _resolved_model.get(account)
CONF_THRESHOLD = {"whip_pan": 0.85, "zoom_punch": 0.85, "luma_fade": 0.9}
CONTEXT_S = 1.5  # clip window padding around the cut


def scene_collection_id(threshold, frame_count=3, model_tag="m15"):
    """VideoDB derives a deterministic id from the extraction config."""
    return f"st{threshold}{model_tag}f{frame_count}"


def existing_collection_id(error, fallback=None):
    """Pull the scene-collection id out of the "already exists" error message.

    Two traps: the message ends with the id followed by a period and trailing
    whitespace (so anchoring on end-of-string finds nothing), and an unanchored
    "id" also matches inside "Inval*id* request", which yields "request:".
    """
    match = re.search(r"\bid\s+(\S+)", str(error))
    return match.group(1).rstrip(". ") if match else fallback


def extract_shots(video, threshold=20, frame_count=3):
    """Extract shots, reusing an existing collection for the same config.

    VideoDB raises InvalidRequestError ("Scenes with given configuration already
    exists") rather than returning the existing collection, so re-runs would fail
    and re-extraction would be paid for twice.
    """
    try:
        return video.extract_scenes(
            extraction_type=SceneExtractionType.shot_based,
            extraction_config={"threshold": threshold, "frame_count": frame_count},
        )
    except InvalidRequestError as e:
        if "already exists" not in str(e):
            raise
        sc_id = existing_collection_id(e, scene_collection_id(threshold, frame_count))
        return video.get_scene_collection(sc_id)


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


def classify_shots_parallel(scene_collection, skip_first=True, workers=WORKERS,
                            account="primary"):
    """Same as classify_shots but concurrent. Returns a list ordered by shot index."""
    scenes = scene_collection.scenes
    targets = [
        (i, s) for i, s in enumerate(scenes)
        if not (skip_first and i == 0) and (s.end - s.start) >= MIN_SHOT_DUR
    ]
    if not targets:
        return []
    model = resolve_model(targets[0][1], account=account)

    def work(item):
        i, scene = item
        try:
            raw = scene.describe(prompt=SHOT_START_PROMPT, model_name=model)
        except Exception as e:
            return i, scene, {"label": "unclear", "confidence": 0.0, "evidence": f"error: {e}"}
        return i, scene, parse_json_reply(raw or "")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(work, targets))


def is_accepted(result) -> bool:
    label = result.get("label")
    conf = float(result.get("confidence") or 0)
    return label in CONF_THRESHOLD and conf >= CONF_THRESHOLD[label]


def validate_detection(scene, result):
    """Second gate: deterministic pixel stats must corroborate the VLM.

    Only runs on VLM-positive candidates (3 small image downloads each). Returns
    (accepted, reason) so rejections stay visible instead of silently vanishing.
    """
    from src.detect import filters

    label = result.get("label")
    if not is_accepted(result):
        return False, "below_confidence"
    try:
        if label == "whip_pan":
            first, settled = filters.shot_whip_stats(scene)
            if not filters.whip_plausible(first, settled):
                return False, f"pixel_veto sharpness={first['sharpness']:.0f}"
        elif label == "luma_fade":
            if not filters.fade_plausible(filters.stats_for(scene.frames[0].url)):
                return False, "pixel_veto luma"
    except Exception as e:
        return True, f"filter_error_passed:{e}"   # never lose a detection to a fetch failure
    return True, "ok"


def detection_window(scene, video_length):
    cut = scene.start
    return max(0.0, cut - CONTEXT_S), min(float(video_length), cut + CONTEXT_S)


__all__ = [
    "extract_shots", "classify_shots", "classify_shots_parallel", "is_accepted",
    "validate_detection", "detection_window", "parse_json_reply",
    "PROMPT_VERSION", "MIN_SHOT_DUR", "CONF_THRESHOLD", "WORKERS",
]
