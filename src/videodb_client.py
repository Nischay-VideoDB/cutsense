"""Single place for VideoDB connection + collection access."""

import os

import videodb
from dotenv import load_dotenv

load_dotenv()

DEFAULT_COLLECTION = "cutsense"

_conns = {}


class NotConfigured(RuntimeError):
    """Raised when the API key for an account is absent, so callers can answer 503."""


def get_conn(account: str = "primary"):
    """`account="legacy"` reads material ingested under the previous API key."""
    if account not in _conns:
        env_key = "VIDEO_DB_API_KEY" if account == "primary" else "VIDEO_DB_API_KEY_LEGACY"
        api_key = os.environ.get(env_key)
        if not api_key:
            raise NotConfigured(f"{env_key} is not set")
        _conns[account] = videodb.connect(api_key=api_key)
    return _conns[account]


def get_collection(name: str = DEFAULT_COLLECTION, create: bool = True, account: str = "primary"):
    conn = get_conn(account)
    coll = next((c for c in conn.get_collections() if c.name == name), None)
    if coll is None and create:
        coll = conn.create_collection(name=name, description="CutSense technique archive")
    return coll
