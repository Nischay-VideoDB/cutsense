"""Run the boundary detectors across the library, skipping work already done.

Match cuts / graphic matches cost 2 vision + 1 text call per cut, so this targets
videos whose library label suggests they contain one, and never re-judges a video
that already has boundary rows.

Usage:
  python scripts/run_boundary_all.py            # hinted videos only
  python scripts/run_boundary_all.py --everything
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db

ROOT = Path(__file__).resolve().parents[1]
HINTS = ("match-cut", "speed-ramping")


def already_judged(db, videodb_id):
    rows = db.execute("SELECT raw_json FROM detections WHERE videodb_id=? LIMIT 400",
                      [videodb_id]).fetchall()
    for r in rows:
        try:
            if json.loads(r["raw_json"] or "{}").get("same_context") is not None:
                return True
        except json.JSONDecodeError:
            continue
    return False


def main(everything=False):
    db = get_db()
    videos = db.execute(
        "SELECT videodb_id, title, technique_hint, duration_s FROM videos"
        " WHERE account='primary' ORDER BY duration_s").fetchall()

    todo = []
    for v in videos:
        hint = v["technique_hint"] or ""
        if not everything and not any(h in hint for h in HINTS):
            continue
        if already_judged(db, v["videodb_id"]):
            print(f"skip (judged): {(v['title'] or '')[:44]}")
            continue
        todo.append(v)

    print(f"\n{len(todo)} videos to judge for boundary techniques\n")
    for i, v in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {(v['title'] or '')[:50]} ({v['duration_s']}s)")
        subprocess.run(
            [str(ROOT / ".venv/bin/python"), "-u", str(ROOT / "scripts/m1_detect_boundary.py"),
             v["videodb_id"], "--match"],
            cwd=ROOT, check=False)


if __name__ == "__main__":
    main("--everything" in sys.argv)
