"""Publish our detections into VideoDB as a Search V2 index.

Detections start life in SQLite because the detectors are ours. Pushing them into
VideoDB as records makes them first-class there: filterable with `query()`, countable
with `aggregate()`, and searchable in the same call as the transcript or scene index.

Every video's index carries the same name, which is how VideoDB scopes a query to a
whole collection — there is no `collection.index()`. Indexes sharing a name must share
field structure, so the record shape below is fixed.
"""

from src.catalog.db import LOCK
from src.detect.prompts import SHIPPING_TECHNIQUES, TECHNIQUE_LABELS

INDEX_NAME = "techniques"

# Which field groups each key belongs to. Declared explicitly rather than letting
# VideoDB infer them, so `technique` is definitely groupable and `confidence` sortable.
FIELDS = {
    "semantic": ["evidence"],
    "filter": ["technique", "label", "verified"],
    "aggregate": ["technique", "label"],
    "sort": ["confidence"],
}


def records_for(db, videodb_id):
    """Detection rows as VideoDB index records. `start`/`end` are reserved; the rest is data."""
    marks = ",".join("?" * len(SHIPPING_TECHNIQUES))
    with LOCK:            # this runs inside a thread pool; the connection is shared
        rows = db.execute(
            f"SELECT technique, confidence, window_start_s, window_end_s, cut_time_s,"
            f" evidence, verified FROM detections WHERE videodb_id=? AND technique IN ({marks})"
            "   AND (verified IS NULL OR verified = 1)"
            " ORDER BY cut_time_s", [videodb_id, *SHIPPING_TECHNIQUES]).fetchall()

    records = []
    for r in rows:
        start = max(0.0, float(r["window_start_s"]))
        end = float(r["window_end_s"])
        if end is None or start is None or end <= start:
            end = start + 0.5          # the API rejects a zero-length record
        records.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "technique": r["technique"],
            "label": TECHNIQUE_LABELS.get(r["technique"], r["technique"]),
            "confidence": float(r["confidence"]) if r["confidence"] is not None else 0.0,
            "cut_time": float(r["cut_time_s"]),
            "verified": bool(r["verified"] == 1),
            "evidence": (r["evidence"] or "")[:500],
        })
    return records


def push(db, video, records=None):
    """Create or replace this video's technique index. Returns the Index, or None."""
    records = records if records is not None else records_for(db, video.id)
    if not records:
        return None

    for existing in video.list_indexes():
        if getattr(existing, "name", None) == INDEX_NAME:
            existing.delete()          # the manifest is immutable; replace it
            break

    return video.index(source=records, name=INDEX_NAME,
                       use_for=["semantic", "query", "aggregate"], fields=FIELDS)


def _rows_of(response):
    return response.get("results", response) if isinstance(response, dict) else (response or [])


def aggregate_by_technique(scope, metric="count"):
    """Group counts (or avg confidence) by technique, computed by VideoDB.

    `scope` is a Collection for the whole library or a Video for one. The response
    returns the metric under `value`, not under the metric name.
    """
    rows = _rows_of(scope.aggregate(index_name=INDEX_NAME, group_by="label", metric=metric))
    out = {}
    for row in rows:
        label = row.get("label")
        if label is None:
            continue
        value = row.get("value", row.get("count"))
        out[label] = round(value, 3) if isinstance(value, float) else value
    return out


def technique_totals(coll):
    """Library-wide counts straight from VideoDB, not from our SQLite mirror."""
    return aggregate_by_technique(coll, "count")
