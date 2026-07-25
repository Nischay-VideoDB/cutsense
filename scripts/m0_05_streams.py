"""M0 step 5: exact-moment clip streams, cross-video compile (study reel), MP4 export.

Uses the two confirmed whip pans in the example video (shots starting 1.4s and 3.56s).
"""

import os

import videodb
from dotenv import load_dotenv
from videodb import timeline as legacy_timeline
from videodb.asset import VideoAsset

load_dotenv()
conn = videodb.connect(api_key=os.environ["VIDEO_DB_API_KEY"])
coll = next(c for c in conn.get_collections() if c.name == "cutsense-m0")

WHIP_VIDEO = "m-z-019f9a8e-a38d-7f23-b961-8f9c3da96a20"   # 6s example, whips at 1.4 & 3.56
TUTORIAL = "m-z-019f9a8e-dd77-7510-a4fb-c1c298b656af"      # 2:07 whip-pan tutorial

video = coll.get_video(WHIP_VIDEO)

# 1. exact-moment clip: whip pan #2 with 1s context either side
clip_url = video.generate_stream(timeline=[(2.6, 4.6)])
print("clip stream (whip #2):", clip_url)

# 2. mini study reel: both whip pans back-to-back via generate_stream
reel_url = video.generate_stream(timeline=[(0.4, 2.4), (2.6, 4.6)])
print("single-video reel:", reel_url)

# 3. cross-video reel via legacy Timeline (clips from two different videos)
tl = legacy_timeline.Timeline(conn)
tl.add_inline(VideoAsset(asset_id=WHIP_VIDEO, start=0.4, end=2.4))
tl.add_inline(VideoAsset(asset_id=WHIP_VIDEO, start=2.6, end=4.6))
tl.add_inline(VideoAsset(asset_id=TUTORIAL, start=10, end=14))
cross_url = tl.generate_stream()
print("cross-video reel:", cross_url)

# 4. MP4 export of the cross-video reel
dl = conn.download(cross_url, "cutsense_m0_reel.mp4")
print("download job:", dl)
