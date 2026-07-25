"""M0 step 2: create cutsense-m0 collection, find candidate test videos, upload.

Test set intent (short, edit-dense):
  1. a whip-pan / transition-heavy edit tutorial or montage (known whip pans)
  2. a fast-cut sneaker/hype ad style edit (zoom punches, cut-on-beat)
  3. a cinematic trailer-style piece (luma fades, match cuts)
"""

import os
import sys

import videodb
from dotenv import load_dotenv

load_dotenv()
conn = videodb.connect(api_key=os.environ["VIDEO_DB_API_KEY"])

COLL_NAME = "cutsense-m0"
coll = next((c for c in conn.get_collections() if c.name == COLL_NAME), None)
if coll is None:
    coll = conn.create_collection(name=COLL_NAME, description="CutSense M0 hands-on validation")
print("collection:", coll.id, coll.name)

if "--search" in sys.argv:
    for q in [
        "whip pan transition examples montage",
        "sneaker commercial edit",
        "fast paced edit music video transitions",
    ]:
        print(f"\n=== youtube_search: {q}")
        try:
            results = conn.youtube_search(q, result_threshold=5, duration="short")
        except Exception as e:
            print("  search failed:", e)
            continue
        for r in results:
            print("  ", r)

urls = [a for a in sys.argv[1:] if a.startswith("http")]
for url in urls:
    print("\nuploading:", url)
    v = coll.upload(url=url)
    print("  ->", v.id, getattr(v, "name", "?"), "length:", getattr(v, "length", "?"))
