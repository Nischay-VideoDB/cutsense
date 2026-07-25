"""M0 step 6: write a 'techniques' scene index with metadata; search it back."""

import os

import videodb
from dotenv import load_dotenv
from videodb import IndexType, SearchType
from videodb.scene import Scene

load_dotenv()
conn = videodb.connect(api_key=os.environ["VIDEO_DB_API_KEY"])
coll = next(c for c in conn.get_collections() if c.name == "cutsense-m0")

WHIP_VIDEO = "m-z-019f9a8e-a38d-7f23-b961-8f9c3da96a20"
video = coll.get_video(WHIP_VIDEO)

scenes = [
    Scene(
        video_id=WHIP_VIDEO, start=0.4, end=2.4,
        description="Whip pan transition: camera whips right with heavy directional motion blur, "
                    "cutting from a student writing at a desk to a student juggling in a classroom.",
        metadata={"technique": "whip_pan", "confidence": 0.96, "cut_time": 1.4},
    ),
    Scene(
        video_id=WHIP_VIDEO, start=2.6, end=4.6,
        description="Whip pan transition: fast lateral camera whip with motion blur smear, "
                    "cutting from the juggling student back to the writing student.",
        metadata={"technique": "whip_pan", "confidence": 0.98, "cut_time": 3.56},
    ),
]

index_id = video.index_scenes(scenes=scenes, name="techniques")
print("techniques index id:", index_id)

records = video.get_scene_index(index_id)
print("index records:", records)

import time
time.sleep(10)  # index becomes searchable ~5-10s after creation

res = video.search(query="whip pan transition with motion blur",
                   search_type=SearchType.semantic, index_type=IndexType.scene)
shots = res.get_shots()
print(f"\nvideo-level semantic search: {len(shots)} shots")
for s in shots:
    print(f"  {s.start:.1f}-{s.end:.1f} score={s.search_score} | {s.text[:80]}")

res2 = coll.search(query="whip pan transition", index_type=IndexType.scene)
shots2 = res2.get_shots()
print(f"\ncollection-level semantic search: {len(shots2)} shots")
for s in shots2:
    print(f"  video={s.video_id[-8:]} {s.start:.1f}-{s.end:.1f} score={s.search_score} | {s.text[:80]}")
if shots2:
    print("\ncompile():", res2.compile())
