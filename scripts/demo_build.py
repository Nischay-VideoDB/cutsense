"""Assemble the demo video from the recorded take.

Cuts the raw Playwright capture down to the beats worth watching, paces each one, and
dresses it in the site's own theme — near-black canvas, one accent colour, the same
type treatment. Segment boundaries come from data/demo/beats.json, which the recorder
writes at capture time, so nothing here is guessed.

Usage: python3 scripts/demo_build.py [--out data/demo/cutsense-demo.mp4]
"""

import json
import subprocess
import sys
from pathlib import Path

DEMO = Path("data/demo")
W, H = 1920, 1080
FPS = 30
BG = "0x0b0b0c"          # site canvas
ACCENT = "0xe8ff43"      # the one accent colour
INK = "0xf2f2f0"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
BOOK = "/System/Library/Fonts/Supplemental/Arial.ttf"


def run(args):
    subprocess.run(args, check=True, capture_output=True)


def esc(text):
    return text.replace(":", r"\:").replace("'", r"\'")


def card(path, lines, seconds=3.0):
    """A title card in the site's theme: accent wordmark, off-white line beneath."""
    draws = []
    y = H // 2 - (len(lines) * 46)
    for i, (text, size, color) in enumerate(lines):
        draws.append(
            f"drawtext=fontfile={BOLD if i == 0 else BOOK}:text='{esc(text)}'"
            f":fontcolor={color}:fontsize={size}:x=(w-tw)/2:y={y}"
            f":alpha='min(1,max(0,(t-0.15)*3))'")
        y += int(size * 1.55)
    run(["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", f"color=c={BG}:s={W}x{H}:d={seconds}:r={FPS}",
         "-vf", ",".join(draws), "-pix_fmt", "yuv420p", "-y", str(path)])


def segment(src, path, start, end, speed=1.0):
    """One beat of the recording, normalised to the output canvas."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG},fps={FPS}")
    if speed != 1.0:
        vf = f"setpts={1/speed:.4f}*PTS,{vf}"
    run(["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", str(src),
         "-vf", vf, "-an", "-pix_fmt", "yuv420p", "-y", str(path)])


def caption(text, start, end):
    """Lower-left caption in the site's type treatment.

    Uses drawtext's own box rather than a separate drawbox: the plate then hugs the
    text exactly, and a standalone dark box is invisible on a canvas this dark anyway.
    """
    on = f"between(t,{start},{end})"
    return (f"drawtext=fontfile={BOLD}:text='{esc(text)}':fontcolor={INK}:fontsize=36"
            f":x=88:y=h-152:box=1:boxcolor=0x16161a@0.96:boxborderw=26:enable='{on}',"
            f"drawbox=x=64:y=h-172:w=7:h=92:color={ACCENT}:t=fill:enable='{on}'")


def main(out_path):
    src = next(p for p in DEMO.glob("*.webm"))
    beats = {b["name"]: b["t"] for b in json.loads((DEMO / "beats.json").read_text())}
    work = DEMO / "cut"
    work.mkdir(exist_ok=True)

    # (label, start, end, speed) — anchored to the recorder's own beat log
    plan = [
        ("hero",     beats["hero"] + 1.0,           beats["analyse_click"] + 3.0, 1.0),
        ("pasted",   beats["report"] - 9.0,         beats["report"] - 1.0,        1.0),
        ("report",   beats["report"] + 6.0,         beats["clip_open"] - 26.0,    1.6),
        ("moments",  beats["clip_open"] - 6.0,      beats["clip_open"] + 4.5,     1.0),
        ("recipe",   beats["recipe"] + 0.5,         beats["library"] - 0.4,       1.0),
        ("library",  beats["library"] + 2.0,        beats["library"] + 16.0,      1.3),
        ("reel",     beats["reel"] + 4.0,           beats["end"] - 0.5,           1.0),
    ]

    parts = []
    intro = work / "00-intro.mp4"
    card(intro, [("CUTSENSE", 96, ACCENT),
                 ("Paste a video. Find out how it was cut.", 42, INK)], 2.6)
    parts.append(intro)

    for i, (label, start, end, speed) in enumerate(plan, start=1):
        path = work / f"{i:02d}-{label}.mp4"
        segment(src, path, start, end, speed)
        parts.append(path)

    outro = work / "99-outro.mp4"
    card(outro, [("246 techniques · 39 videos · every one audited", 44, INK),
                 ("cutsense-production.up.railway.app", 40, ACCENT)], 3.4)
    parts.append(outro)

    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    joined = work / "joined.mp4"
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "-y", str(joined)])

    # captions land on the assembled timeline, measured from each part's real duration
    def duration(path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", str(path)],
                             capture_output=True, text=True).stdout.strip()
        return float(out)

    offsets, running = {}, 0.0
    for p in parts:
        offsets[p.stem] = (running, running + duration(p))
        running += duration(p)

    lines = {
        "01-hero":    "Paste any video — it reads the edit, not the transcript",
        "02-pasted":  "Every technique it uses, with the cut rhythm",
        "03-report":  "Whip pan x21 — each one a playable moment",
        "04-moments": "Two seconds of the exact cut, not a timestamp",
        "05-recipe":  "A recipe to rebuild it: Remotion, VideoDB, Premiere, Resolve",
        "06-library": "Library-wide counts aggregated by VideoDB",
        "07-reel":    "One study reel, stitched across videos",
    }
    filters = [caption(text, offsets[k][0] + 0.4, offsets[k][1] - 0.3)
               for k, text in lines.items() if k in offsets]
    filters.append(f"fade=t=in:st=0:d=0.5,fade=t=out:st={running - 0.6:.2f}:d=0.6")

    run(["ffmpeg", "-v", "error", "-i", str(joined), "-vf", ",".join(filters),
         "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", "-y", str(out_path)])
    print(f"wrote {out_path} ({duration(out_path):.1f}s, {out_path.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else DEMO / "cutsense-demo.mp4"
    main(out)
