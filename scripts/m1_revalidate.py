"""Apply pixel-stat gates to detections already stored, without re-running the VLM.

Needed whenever filters change: the expensive part (vision classification) is
already in SQLite, so revalidation is just image stats over candidate shots.

Usage: python scripts/m1_revalidate.py [--apply]   # dry-run unless --apply
"""

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import get_db
from src.detect import filters
from src.videodb_client import get_collection

GATED = ("whip_pan", "luma_fade")


def verdict(scene, technique):
    try:
        if technique == "whip_pan":
            first, settled = filters.shot_whip_stats(scene)
            ok = filters.whip_plausible(first, settled)
            return ok, f"sharpness={first['sharpness']:.0f}"
        first = filters.stats_for(scene.frames[0].url)
        return filters.fade_plausible(first), f"luma={first['luma']:.0f}"
    except Exception as e:
        return True, f"filter_error:{e}"


def main(apply=False):
    db = get_db()
    coll = get_collection()
    rows = list(db.execute(
        "SELECT d.id, d.videodb_id, d.shot_idx, d.technique, d.confidence, d.cut_time_s,"
        " v.title FROM detections d JOIN videos v ON v.videodb_id=d.videodb_id"
        f" WHERE d.technique IN ({','.join('?' * len(GATED))}) ORDER BY d.videodb_id, d.cut_time_s",
        GATED))
    print(f"{len(rows)} gated detections to revalidate (apply={apply})\n")

    scenes_by_video = {}
    tally = Counter()
    for r in rows:
        vid = r["videodb_id"]
        if vid not in scenes_by_video:
            v = coll.get_video(vid)
            scenes_by_video[vid] = v.get_scene_collection("st20m15f3").scenes

    def check(r):
        scenes = scenes_by_video[r["videodb_id"]]
        scene = min(scenes, key=lambda s: abs(s.start - r["cut_time_s"]))
        ok, detail = verdict(scene, r["technique"])
        return r, ok, detail

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, rows))

    for r, ok, detail in results:
        tally[(r["technique"], "keep" if ok else "veto")] += 1
        if not ok:
            print(f"  VETO {r['technique']:10s} @{r['cut_time_s']:7.2f}s conf={r['confidence']}"
                  f"  {detail}  [{(r['title'] or '')[:32]}]")
            if apply:
                db.execute("UPDATE detections SET technique=?, evidence=? WHERE id=?",
                           [f"rejected:{r['technique']}", f"pixel_veto {detail}", r["id"]])
    if apply:
        db.commit()

    print("\nsummary:")
    for (tech, outcome), n in sorted(tally.items()):
        print(f"  {tech:10s} {outcome:5s} {n}")
    kept = sum(n for (_, o), n in tally.items() if o == "keep")
    print(f"  kept {kept} / {len(rows)}")
    if not apply:
        print("\ndry run — re-run with --apply to persist")


if __name__ == "__main__":
    main("--apply" in sys.argv)
