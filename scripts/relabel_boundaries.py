"""Re-derive boundary labels from stored judge output — no API calls.

The judge commits to `same_context` and `composition_match`, both kept in
detections.raw_json, so adding or changing a derived label (e.g. graphic_match)
is a pure local recompute.

Usage: python scripts/relabel_boundaries.py [--apply]
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db
from src.detect import boundary as bd


def main(apply=False):
    db = get_db()
    rows = list(db.execute("SELECT id, technique, raw_json FROM detections"))
    changes, tally = [], Counter()

    for r in rows:
        try:
            payload = json.loads(r["raw_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if payload.get("same_context") is None:
            continue   # not a boundary judgement
        derived = bd.match_cut_label(payload)
        want = derived if bd.accepted_boundary(payload) else f"rejected:{derived}"
        tally[want] += 1
        if want != r["technique"]:
            changes.append((r["id"], r["technique"], want))

    print(f"{sum(tally.values())} boundary judgements | {len(changes)} labels change")
    for _, old, new in changes[:15]:
        print(f"  {old:22s} -> {new}")
    if len(changes) > 15:
        print(f"  ... and {len(changes) - 15} more")

    print("\nresulting distribution:")
    for label, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {label:24s} {n}")

    if apply and changes:
        db.executemany("UPDATE detections SET technique=? WHERE id=?",
                       [(new, det_id) for det_id, _, new in changes])
        db.commit()
        print(f"\napplied {len(changes)} updates")
    elif not apply:
        print("\ndry run — re-run with --apply to persist")


if __name__ == "__main__":
    main("--apply" in sys.argv)
