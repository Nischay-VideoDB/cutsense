"""Export the tracked catalog snapshot that seeds a fresh deploy.

Run after any detection run, then commit library/catalog-snapshot.json.

Usage: python scripts/export_snapshot.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db
from src.catalog.snapshot import SNAPSHOT_PATH, export_snapshot

if __name__ == "__main__":
    counts = export_snapshot(get_db())
    print(f"wrote {SNAPSHOT_PATH.relative_to(Path.cwd())}: "
          + ", ".join(f"{k}={v}" for k, v in counts.items()))
