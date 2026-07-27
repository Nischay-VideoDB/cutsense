# Demo video plan

Target: **2 minutes**, screen recording with voiceover, no edit tricks needed.
Live: https://cutsense-production.up.railway.app

The judging split is technical execution 40 / creativity 30 / VideoDB depth 30, so the
run of show is built to hit all three explicitly rather than hoping they are inferred.

## The one sentence the demo has to land

> Paste a video and CutSense tells you what editing techniques it uses, where, and how
> to rebuild each one — by reading the picture, not the transcript.

Say it in the first ten seconds. Everything after is evidence.

## Pre-flight (do this before recording)

1. **Warm the app.** Open the site, load `/library`, open one `/video/…` report. First
   requests generate assets; you do not want that latency on camera.
2. **Pre-analyse the video you will "paste."** Run it once beforehand so the result is
   cached. A cold analysis takes 1.5–2.5 minutes — far too long to sit through.
   For the live paste, either start it and cut away, or paste a URL already in the
   gallery so the report returns immediately.
3. **Browser at 1280×800**, bookmarks bar hidden, zoom 100%, dark OS theme.
4. **Have these three tabs ready**: the home page, a strong report page
   (`/video/…` for the tutorial or the Friesenjung music video), and `/library`.
5. Mute system notifications.

## Run of show

| time | on screen | what you say |
|---|---|---|
| 0:00–0:12 | Home page, hero visible. Paste a URL and hit Analyse. | "Editors learn by reverse-engineering other people's work. This reads the edit itself — every cut, every transition — and tells you how it was done." |
| 0:12–0:20 | Progress bar moves through *finding the cuts → reading each cut*. Cut away before it finishes. | "It pulls the shot boundaries out of the video, then reads the frames at every single cut." |
| 0:20–0:45 | **Report page.** Headline first: *"15x whip pan, 2x zoom punch — cut at 35 cuts/min, average shot 1.7s."* Scroll the metric row and the pacing curve. | "Here is that video's edit, described. Not a transcript — the techniques, and the rhythm they are cut at." |
| 0:45–1:05 | Scroll to the **Whip Pan** block. Hover two or three moment thumbnails, click one, let the 2-second clip play in the sheet. | "Every hit is a playable two-second clip of the exact moment. You can see the smear in the thumbnail before you even click." |
| 1:05–1:25 | Expand **"How to recreate it."** Scroll past the effect-spec table, the Remotion code, the VideoDB programmable-editing block. | "And each one comes with a recipe — the exact spec, then working Remotion code, then how to do it in Premiere, Resolve or CapCut." |
| 1:25–1:40 | Scroll to **"Same technique elsewhere in the library."** Click through to one. | "The library is 46 real ads, music videos and films — so you can compare your cut against how other people did the same move." |
| 1:40–1:55 | `/library`: the **insights strip** ("aggregated by VideoDB · index techniques"), then **"Make a study reel of these"** → the stitched reel plays. | "Every detection is published back into VideoDB as a searchable index, so these library-wide numbers are computed by VideoDB itself. And it will stitch every instance into one study reel." |
| 1:55–2:00 | Hold on the reel playing. | "246 techniques across 39 videos — every one of them audited." |

## Features to show, in priority order

**Must appear** (these carry the score):
1. Paste → report (the product's whole thesis)
2. A technique block with playable moments (whip pan — strongest and most legible)
3. A recipe expanded, showing Remotion **and** the VideoDB programmable-editing section
4. The insights strip labelled *aggregated by VideoDB* (depth criterion, in one glance)
5. A study reel stitching across videos (editor API, and it is a satisfying finish)

**Show if time allows**: creator style profile (`/creator/ONHA` — the LLM-written
signature reads well), the plain-language ask box, MP4 export on a reel, file upload.

**Do not show**: match cut, graphic match, speed ramp. They are real but thin (4, 7 and
7 detections) and unaudited — a judge clicking into them finds the weakest surface.

## The honesty beat (worth 10 seconds)

Somewhere around 1:50, say one line about measurement:

> "An independent second model audited all 582 detections and refuted 311 of them —
> those are hidden. Whip pan measures 60% precision, and we say so rather than claiming
> it just works."

Most hackathon demos assert accuracy. Naming a real number, and showing that the weak
ones were withheld, reads as engineering maturity — and it is the thing the LEARNINGS
doc can back up if anyone checks.

## Risks and fallbacks

| risk | fallback |
|---|---|
| Live analysis runs long | Paste a URL already in the gallery — the report returns instantly |
| A clip stalls (HLS URLs expire ~24h) | Reload the page; the stream regenerates on request. Warm the exact clips beforehand |
| Reel build fails | Have a previously built reel URL open in a spare tab |
| The API key's model tier is exhausted mid-demo | Nothing in the demo path needs live model calls if everything is pre-warmed — thumbnails and reports are served from the catalog |

## If you need a 30-second cut

Home → paste (cut) → report headline → whip-pan grid → one clip playing → recipe
open → study reel. Drop the library, profiles and the honesty beat.
