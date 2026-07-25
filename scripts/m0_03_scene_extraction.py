"""M0 step 3: shot-based scene extraction at multiple thresholds; dump timing stats."""

import json
import os
import statistics
import sys

import videodb
from dotenv import load_dotenv
from videodb import SceneExtractionType

load_dotenv()
conn = videodb.connect(api_key=os.environ["VIDEO_DB_API_KEY"])
coll = next(c for c in conn.get_collections() if c.name == "cutsense-m0")

video_id = sys.argv[1]
thresholds = [int(t) for t in sys.argv[2:]] or [15, 20, 25]
video = coll.get_video(video_id)
print("video:", video.id, getattr(video, "name", "?"))

out = {}
for t in thresholds:
    sc = video.extract_scenes(
        extraction_type=SceneExtractionType.shot_based,
        extraction_config={"threshold": t, "frame_count": 3},
        force=True,
    )
    scenes = sc.scenes
    durs = [s.end - s.start for s in scenes]
    print(f"\nthreshold={t}: {len(scenes)} shots | scene_collection={sc.id}")
    if durs:
        print(f"  dur min/med/max: {min(durs):.2f}/{statistics.median(durs):.2f}/{max(durs):.2f}s")
    print("  boundaries:", ", ".join(f"{s.start:.1f}" for s in scenes[:25]), "...")
    out[t] = {
        "scene_collection_id": sc.id,
        "shots": [
            {"start": s.start, "end": s.end,
             "frames": [{"time": f.frame_time, "url": f.url} for f in s.frames]}
            for s in scenes
        ],
    }

os.makedirs("data/m0", exist_ok=True)
path = f"data/m0/scenes_{video_id}.json"
with open(path, "w") as fh:
    json.dump(out, fh, indent=1)
print("\nsaved:", path)
