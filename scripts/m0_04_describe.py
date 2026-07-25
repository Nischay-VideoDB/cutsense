"""M0 step 4: VLM technique classification test via scene.describe().

Runs a structured technique prompt on every shot of a scene collection.
Ground truth (whip-pan example video, st20): shot 3 (3.56-5.84) opens with whip-pan blur;
shots 0-2 are normal; shot 4 is a 0.04s stub.
"""

import os
import sys

import videodb
from dotenv import load_dotenv

load_dotenv()
conn = videodb.connect(api_key=os.environ["VIDEO_DB_API_KEY"])
coll = next(c for c in conn.get_collections() if c.name == "cutsense-m0")

video_id, sc_id = sys.argv[1], sys.argv[2]
video = coll.get_video(video_id)
sc = video.get_scene_collection(sc_id)

PROMPT = """You are analyzing frames from ONE shot of an edited video to detect editing techniques.
The frames are sampled in time order (first frame = the moment right after a cut).

Classify what happens at the START of this shot, choosing exactly one label:
- whip_pan: first frame(s) show strong directional motion blur smearing the whole image, then the image settles
- zoom_punch: sudden scale jump on the same framing
- luma_fade: first frame(s) are near-black or near-white
- hard_cut: shot starts clean and sharp, no transition artifact
- unclear: cannot tell

Respond ONLY with JSON: {"label": "...", "confidence": 0.0-1.0, "evidence": "one sentence"}"""

for i, scene in enumerate(sc.scenes):
    try:
        desc = scene.describe(prompt=PROMPT)
    except Exception as e:
        desc = f"ERROR: {e}"
    print(f"shot {i} [{scene.start:.2f}-{scene.end:.2f}] ({len(scene.frames)} frames):")
    print("   ", desc)
