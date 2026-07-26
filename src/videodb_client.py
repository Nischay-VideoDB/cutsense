"""Single place for VideoDB connection + collection access."""

import os

import videodb
from dotenv import load_dotenv

load_dotenv()

DEFAULT_COLLECTION = "cutsense"

_conns = {}


def get_conn(account: str = "primary"):
    """`account="legacy"` reads material ingested under the previous API key."""
    if account not in _conns:
        env_key = "VIDEO_DB_API_KEY" if account == "primary" else "VIDEO_DB_API_KEY_LEGACY"
        _conns[account] = videodb.connect(api_key=os.environ[env_key])
    return _conns[account]


def get_collection(name: str = DEFAULT_COLLECTION, create: bool = True, account: str = "primary"):
    conn = get_conn(account)
    coll = next((c for c in conn.get_collections() if c.name == name), None)
    if coll is None and create:
        coll = conn.create_collection(name=name, description="CutSense technique archive")
    return coll
