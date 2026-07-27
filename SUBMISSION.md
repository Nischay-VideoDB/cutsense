# CutSense — hackathon submission

**Live:** https://cutsense-production.up.railway.app
**Repo:** https://github.com/falgunitripathi/cutsense

## Description (200 words max)

CutSense answers the question editors ask constantly: how was this cut?

Paste a video and CutSense reads the edit itself, not the transcript. VideoDB's
shot-based scene extraction gives frame-accurate cut boundaries — those boundaries are
the edits. At each cut we sample frames and classify what happened with
`scene.describe()`, gated first by deterministic pixel and motion signals computed
locally, so the vision model only ever judges plausible candidates. Six techniques
ship: whip pan, zoom punch, match cut, graphic match, speed ramp, luma fade.

Every result is a playable two-second clip (`generate_stream`), a poster frame
(`generate_thumbnail`), and a recipe for rebuilding the move in Premiere, Resolve,
CapCut, Remotion, or VideoDB's own editor timeline. Ask for a study reel of every whip
pan and the editor API stitches one across videos, exportable to MP4.

A 46-video library of real ads, music videos and films supplies the same technique in
other people's work for comparison, plus per-creator style profiles — cut rate, rhythm,
technique mix — aggregated through VideoDB indexes.

An independent second model audited all 582 detections; refuted ones are hidden. We
report measured precision instead of claiming accuracy.

**Demo plan:** [docs/DEMO.md](docs/DEMO.md)

## VideoDB surfaces used

Ingest (`upload` by URL and file, `youtube_search`) · shot-based `extract_scenes` and
frames · `scene.describe` with model-tier fallback · `index` / `query` / `aggregate`
(Search V2) · scene indexes with metadata · `semantic_search` · `generate_text` ·
`generate_thumbnail` · `generate_stream` clip windows · `editor` Timeline/Track/Clip
with transitions · `download` for MP4 export.

## Judged claims, and the evidence behind them

| claim | evidence |
|---|---|
| detection is measured, not asserted | independent second-model audit of all 582 detections; per-technique precision reported in `docs/LEARNINGS.md` |
| whip pan 60%, luma fade 48%, zoom punch 75% | audit verdicts stored per detection in `detections.verified` |
| zoom punch improved 14% → 75% | scale-jump gate calibrated on the audited labels (`src/detect/scale_jump.py`) |
| three techniques deliberately withheld | shake/glitch/split-screen signals calibrated against 140 windows and failed to separate (`scripts/m2_calibrate_look.py`) |
