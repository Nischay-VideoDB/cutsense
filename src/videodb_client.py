"""Single place for VideoDB connection + collection access."""

import os

import videodb
from dotenv import load_dotenv

load_dotenv()

_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = videodb.connect(api_key=os.environ["VIDEO_DB_API_KEY"])
    return _conn


def get_collection(name: str = "cutsense-m0", create: bool = True):
    conn = get_conn()
    coll = next((c for c in conn.get_collections() if c.name == name), None)
    if coll is None and create:
        coll = conn.create_collection(name=name, description="CutSense")
    return coll
