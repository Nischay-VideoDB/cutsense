"""M0 step 1: verify API key, list collections, check usage/billing if available."""

import os

import videodb
from dotenv import load_dotenv

load_dotenv()

conn = videodb.connect(api_key=os.environ["VIDEO_DB_API_KEY"])
coll = conn.get_collection()
print("connected OK")
print("default collection:", coll.id, "|", coll.name)

colls = conn.get_collections()
print(f"{len(colls)} collection(s):")
for c in colls:
    print("  -", c.id, c.name)

videos = coll.get_videos()
print(f"{len(videos)} video(s) in default collection")
for v in videos:
    print("  -", v.id, getattr(v, "name", "?"), getattr(v, "length", "?"))
