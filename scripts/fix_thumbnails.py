"""Repair thumbnails that are missing or visually empty.

Two separate faults were found in an audit of 582 detections:
  * 11 had no thumbnail at all — generate_thumbnail failed for that timestamp
  * 10 were near-solid-colour frames (a 755-byte PNG is effectively black). Accurate
    for a luma fade, useless as a poster.

Repair strategy, cheapest first:
  1. try neighbouring timestamps and keep the most informative frame
  2. fall back to a frame image from the shot's scene collection, which already
     exists and costs nothing
A whip pan's blur sits exactly at the cut and is the whole point, so a frame is only
replaced when it carries almost no detail — never merely because it is blurry.

Usage: python scripts/fix_thumbnails.py [--apply] [--all]
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalog.db import LOCK, get_db
from src.detect import pipeline as pl
from src.detect.filters import load_gray
from src.detect.prompts import SHIPPING_TECHNIQUES
from src.videodb_client import get_collection

OFFSETS = (0.0, 0.4, -0.4, 0.8, 1.2)
MIN_DETAIL = 6.0       # std-dev of grey levels; below this the frame reads as blank
BLANK_BYTES = 4000     # PNG size proxy: a near-uniform frame compresses tiny
WORKERS = 6


def byte_size(url):
    """Cheap blankness proxy — a HEAD beats downloading 571 images to measure detail."""
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(resp.headers.get("content-length") or 0)
    except Exception:
        return -1


def detail_of(url):
    try:
        gray = load_gray(url, max_side=200)
        return float(np.std(gray))
    except Exception:
        return -1.0


def candidate_thumbs(video, cut_time, duration):
    """Yield (offset, url, detail) for timestamps around the cut."""
    for off in OFFSETS:
        t = cut_time + off
        if t < 0 or (duration and t > duration - 0.05):
            continue
        try:
            thumb = video.generate_thumbnail(time=float(t))
            url = getattr(thumb, "url", thumb)
        except Exception:
            continue
        if url:
            yield off, url, detail_of(url)


def frame_fallback(video, cut_time):
    """A frame image from the shot containing this cut — already generated, free."""
    try:
        scenes = pl.extract_shots(video).scenes
    except Exception:
        return None
    for scene in scenes:
        if scene.start - 0.05 <= cut_time <= scene.end + 0.05:
            best = None
            for frame in scene.frames:
                d = detail_of(frame.url)
                if best is None or d > best[1]:
                    best = (frame.url, d)
            return best
    return None


def main(apply=False, everything=False):
    db = get_db()
    coll = get_collection()
    marks = ",".join("?" * len(SHIPPING_TECHNIQUES))
    rows = db.execute(
        f"SELECT d.id, d.videodb_id, d.cut_time_s, d.technique, v.duration_s, v.account,"
        f" a.thumbnail_url FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
        f" LEFT JOIN clip_assets a ON a.detection_id = d.id"
        f" WHERE d.technique IN ({marks})", SHIPPING_TECHNIQUES).fetchall()

    with ThreadPoolExecutor(max_workers=16) as pool:
        sizes = dict(zip(
            [r["id"] for r in rows if r["thumbnail_url"]],
            pool.map(byte_size, [r["thumbnail_url"] for r in rows if r["thumbnail_url"]])))

    todo = []
    for r in rows:
        if not r["thumbnail_url"]:
            todo.append((r, "missing"))
        elif everything or sizes.get(r["id"], 0) < BLANK_BYTES:
            todo.append((r, "blank"))
    print(f"{len(rows)} detections · {len(todo)} need repair "
          f"({sum(1 for _, k in todo if k == 'missing')} missing, "
          f"{sum(1 for _, k in todo if k == 'blank')} blank)")

    videos = {}

    def repair(item):
        r, kind = item
        key = (r["account"] or "primary", r["videodb_id"])
        try:
            if key not in videos:
                videos[key] = get_collection(account=key[0]).get_video(r["videodb_id"])
            video = videos[key]
        except Exception as e:
            return r, kind, None, f"video unavailable: {type(e).__name__}"

        best = None
        for off, url, detail in candidate_thumbs(video, r["cut_time_s"], r["duration_s"]):
            if best is None or detail > best[2]:
                best = (off, url, detail)
            if detail >= MIN_DETAIL * 2:      # good enough, stop paying
                break
        if best and best[2] >= MIN_DETAIL:
            return r, kind, best[1], f"offset {best[0]:+.1f}s detail {best[2]:.1f}"

        fb = frame_fallback(video, r["cut_time_s"])
        if fb and fb[1] >= MIN_DETAIL:
            return r, kind, fb[0], f"shot frame detail {fb[1]:.1f}"
        if best:
            return r, kind, best[1], f"best available detail {best[2]:.1f}"
        return r, kind, None, "no candidate produced a frame"

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(repair, todo))

    fixed = 0
    for r, kind, url, note in results:
        flag = "fixed " if url else "FAILED"
        print(f"  {flag} #{r['id']:5d} {r['technique']:13s} @{r['cut_time_s']:7.2f}s  {note}")
        if url and apply:
            with LOCK:
                db.execute(
                    "INSERT INTO clip_assets (detection_id, thumbnail_url) VALUES (?,?)"
                    " ON CONFLICT(detection_id) DO UPDATE SET thumbnail_url=excluded.thumbnail_url",
                    [r["id"], url])
                db.commit()
            fixed += 1
    print(f"\n{fixed} updated" if apply else "\ndry run — re-run with --apply")


if __name__ == "__main__":
    main("--apply" in sys.argv, "--all" in sys.argv)
