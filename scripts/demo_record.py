"""Record the demo: drive the live app with Playwright and capture real footage.

Follows the demo-recording approach — capture genuine product footage first, then
assemble. This drives the deployed site through the run of show in docs/DEMO.md and
writes a webm per take, which `demo_build.sh` trims and titles.

Everything is paced deliberately: real cursor moves, pauses to let clips play, and no
cold analysis (that takes minutes and is pre-warmed instead).

Usage: python3 scripts/demo_record.py [--base URL] [--out DIR]
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://cutsense-production.up.railway.app"
OUT = Path("data/demo")
SIZE = {"width": 1280, "height": 800}

# a report with a strong whip-pan block, and the technique page behind it
# 21 whip pans and nothing from the thin techniques — the strongest surface to film
REPORT_VIDEO = "m-z-019f9f8b-5558-7721-a464-23fb1e42d4b8"   # Whiplash
PASTE_URL = "https://www.youtube.com/watch?v=jDiG5VyEZtw"   # already analysed: returns fast


def settle(page, ms=900):
    page.wait_for_timeout(ms)


def images_ready(page, timeout=25000):
    """Wait for every visible thumbnail to actually paint.

    Recording over the network catches half-loaded grids, and a wall of black tiles
    reads as a broken product rather than a loading one.
    """
    try:
        page.wait_for_function(
            """() => {
                const imgs = [...document.querySelectorAll('img')];
                return imgs.length > 0 && imgs.every(i => i.complete && i.naturalWidth > 0);
            }""", timeout=timeout)
    except Exception:
        pass          # never let a slow asset abort the take


def glide(page, x, y, steps=18):
    """Move the cursor visibly — a jumping pointer reads as a slideshow."""
    page.mouse.move(x, y, steps=steps)


def record(base, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    beats = []
    t0 = None

    def beat(name):
        """Log when each moment actually happened, so captions anchor to real time."""
        beats.append({"name": name, "t": round(time.time() - t0, 2)})
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        context = browser.new_context(
            viewport=SIZE, device_scale_factor=2,
            record_video_dir=str(out_dir), record_video_size=SIZE,
            color_scheme="dark",
        )
        page = context.new_page()
        t0 = time.time()

        # 1 — the hero, then paste a URL
        beat("hero")
        page.goto(base, wait_until="networkidle")
        settle(page, 1600)
        glide(page, 640, 470)
        page.click("#analyse-url")
        page.type("#analyse-url", PASTE_URL, delay=42)
        settle(page, 700)
        glide(page, 1150, 470)
        beat("analyse_click")
        page.click("#analyse-btn")
        settle(page, 2600)                     # progress bar moves, then it resolves
        page.wait_for_url("**/video/**", timeout=60_000)
        images_ready(page)
        settle(page, 2200)                     # the report for what we just pasted

        # 2 — the report for that video (deep link, so it is instant on camera)
        beat("report")
        page.goto(f"{base}/video/{REPORT_VIDEO}", wait_until="networkidle")
        images_ready(page)
        settle(page, 1800)
        page.mouse.wheel(0, 380); settle(page, 1700)     # metrics + pacing curve
        block = page.query_selector(".tblock")           # the first technique block
        if block:
            block.scroll_into_view_if_needed()
            images_ready(page)
            settle(page, 1600)

        # 3 — hover the moments so the thumbnails read, then open one
        for x in (250, 420, 590):
            glide(page, x, 430); settle(page, 600)
        beat("clip_open")
        page.mouse.click(250, 430)
        settle(page, 4200)                     # the 2s clip loops twice

        page.keyboard.press("Escape")
        settle(page, 900)

        # 4 — the recipe
        beat("recipe")
        recipe = page.query_selector("details.recipe-wrap summary")
        if recipe:
            recipe.scroll_into_view_if_needed()
            settle(page, 500)
            recipe.click()
            settle(page, 1400)
            page.mouse.wheel(0, 620); settle(page, 1800)   # spec table -> Remotion code
            page.mouse.wheel(0, 620); settle(page, 1600)   # programmable editing

        # 5 — the library: insights strip computed by VideoDB, then the grid
        beat("library")
        page.goto(f"{base}/library", wait_until="networkidle")
        images_ready(page)
        settle(page, 2600)
        page.mouse.wheel(0, 260); settle(page, 1600)

        # 6 — a study reel, stitched across videos
        beat("reel")
        reel = page.query_selector("#reelbtn")
        if reel:
            reel.scroll_into_view_if_needed()
            glide(page, 1080, 200)
            reel.click()
            page.wait_for_selector("#reel-player", timeout=90_000)
            settle(page, 7000)                 # let the stitched reel actually play

        beat("end")
        context.close()
        browser.close()
    (out_dir / "beats.json").write_text(json.dumps(beats, indent=1))
    print("beats:", ", ".join(f"{b['name']}@{b['t']}s" for b in beats))

    takes = sorted(out_dir.glob("*.webm"))
    print(f"recorded {len(takes)} file(s):")
    for t in takes:
        print(f"  {t}  {t.stat().st_size // 1024}KB")
    return takes


if __name__ == "__main__":
    args = sys.argv[1:]
    base = args[args.index("--base") + 1] if "--base" in args else BASE
    out = Path(args[args.index("--out") + 1]) if "--out" in args else OUT
    record(base, out)
