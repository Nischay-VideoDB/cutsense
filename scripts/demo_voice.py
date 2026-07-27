"""Generate the demo voiceover with ElevenLabs, one clip per beat.

One mp3 per beat rather than a single track: the build then sets each segment's
length from its own narration, so picture and voice stay locked without hand-timing
anything. Clips are cached — re-running only regenerates lines whose text changed.

Usage: python3 scripts/demo_voice.py
"""

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

OUT = Path("data/demo/vo")
ENV = Path("/Users/shivanshutripathi/Desktop/theAIVideo-Studio/projects/videodb-youtube-videos/.env")
VOICE = "86SOy9VyOePcRbIneYDa"
MODEL = "eleven_multilingual_v2"     # v3 is not exposed on the public TTS endpoint

# One line per beat. Written to be read aloud: short clauses, no nested commas, and
# the claim always before the detail.
LINES = {
    "01-hero":    "Editors learn by reverse engineering other people's work. CutSense reads "
                  "the edit itself. Paste any video.",
    "02-pasted":  "It finds every cut, then tells you which techniques were used, and how "
                  "fast the thing is cut.",
    "03-report":  "Twenty one whip pans in this one. Each is a moment you can actually play.",
    "04-moments": "Not a timestamp to go hunting for. The exact two seconds around the cut.",
    "05-recipe":  "And a recipe to rebuild it. The spec, working Remotion code, then Premiere, "
                  "Resolve and CapCut.",
    "06-library": "Forty six real ads, music videos and films sit behind it. These counts are "
                  "aggregated by VideoDB itself.",
    "07-reel":    "One click stitches every instance into a study reel, across videos.",
    "99-outro":   "Two hundred and forty six techniques. Every one of them audited.",
}


def api_key():
    for line in ENV.read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no ELEVENLABS_API_KEY found")


def say(key, text, path):
    body = json.dumps({
        "text": text,
        "model_id": MODEL,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75, "style": 0.15},
    }).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}",
        data=body, method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r:
        path.write_bytes(r.read())


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    key = api_key()
    manifest = {}
    for name, text in LINES.items():
        stamp = hashlib.sha1(f"{MODEL}:{VOICE}:{text}".encode()).hexdigest()[:10]
        path = OUT / f"{name}-{stamp}.mp3"
        if not path.exists():
            try:
                say(key, text, path)
            except Exception as e:
                detail = getattr(e, "read", lambda: b"")()[:200]
                print(f"  {name}: FAILED {type(e).__name__} {detail}")
                continue
        secs = duration(path)
        manifest[name] = {"file": str(path), "seconds": round(secs, 2), "text": text}
        print(f"  {name:11s} {secs:5.2f}s  {path.name}")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    total = sum(v["seconds"] for v in manifest.values())
    print(f"\n{len(manifest)}/{len(LINES)} clips · {total:.1f}s of narration")


if __name__ == "__main__":
    sys.exit(main())
