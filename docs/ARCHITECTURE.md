# CutSense — Architecture & Implementation Plan

> Grounded in three deep research passes over docs.videodb.io and github.com/video-db (see [LEARNINGS.md](LEARNINGS.md)).
> Principle: **lean on VideoDB for everything it does natively** (ingest, cut detection, VLM description, semantic search, clip streaming, reel compilation, MP4 export, thumbnails). Our code is the technique layer on top.

## 1. System overview

```
                        ┌─────────────────────────────────────────────┐
                        │                  VideoDB                     │
 reference videos ────► │ upload → transcode → shot-based scene        │
 (files / YouTube URLs) │ extraction → frames → VLM describe →         │
                        │ named scene indexes (+ metadata) →           │
                        │ semantic search / query / aggregate →        │
                        │ HLS clip streams · compile() · editor        │
                        │ Timeline · MP4 download jobs · thumbnails    │
                        └───────────────┬─────────────────────────────┘
                                        │ videodb-python SDK
                        ┌───────────────▼─────────────────────────────┐
                        │            CutSense backend (Python)         │
                        │ ingest orchestrator · technique detector     │
                        │ (prompt pipeline + validators) · local       │
                        │ catalog (SQLite) · recipe generator ·        │
                        │ profile analytics · reel builder             │
                        │                FastAPI                       │
                        └───────────────┬─────────────────────────────┘
                                        │ REST/JSON
                        ┌───────────────▼─────────────────────────────┐
                        │  Web UI (React) — search box → clip grid     │
                        │  (HLS player) → recipe panel → reel builder  │
                        │  → style profiles                            │
                        └─────────────────────────────────────────────┘
```

Stack: **Python 3.11 + videodb SDK + FastAPI + SQLite** backend; **React + Vite + hls.js** frontend. (Same stack shape as AEO Tracker — known-good, fast to ship.)

## 2. Technique vocabulary (scoped, v1)

The 40% risk is detection. We ship a **small vocabulary that always works** — 8 techniques, each chosen because it's detectable from shot-boundary frames + timing signals:

| # | Technique | Primary signal | Detector inputs |
|---|-----------|----------------|-----------------|
| 1 | Hard cut (baseline) | shot boundary | scene timestamps (free) |
| 2 | Whip pan | extreme directional motion blur at boundary | last frames of shot A + first of shot B |
| 3 | Zoom punch | same framing, sudden scale change across cut | boundary frame pair |
| 4 | Match cut | compositional similarity across cut, different content | boundary frame pair |
| 5 | Speed ramp | motion smear/velocity change within shot | multi-frame sample within shot |
| 6 | Luma fade / dip to black-white | brightness collapse at boundary | boundary frames (cheap pixel stats + VLM confirm) |
| 7 | Shake / impact frame | high-frequency displacement, flash frames | frames around boundary |
| 8 | Cut-on-beat (pacing) | cut times align to audio beat grid | scene timestamps + audio analysis |

Stretch (only if v1 is solid): J/L cuts (audio/video offset — needs transcript+scene alignment), split screen, glitch.

## 3. Ingestion & indexing pipeline

Per video, orchestrated by `src/ingest/` with state tracked in SQLite (resumable; never re-pay for a completed stage):

**Stage A — Upload.** `coll.upload(url=...)` (YouTube supported) or `file_path=`. Store `video_id`, title, source, creator/brand tags, duration.

**Stage B — Cut extraction.** `video.extract_scenes(extraction_type=shot_based, extraction_config={"threshold": T, "frame_count": 3})` → `SceneCollection`. Shot boundaries ARE the edits. Tune `threshold` in M1 on a calibration set (higher = fewer splits). This alone yields: cut count, cut-length distribution, pacing curve.

**Stage C — Technique detection (our core IP).** Two-tier to control cost and false positives:
1. **Cheap filters first** (local, free): boundary-frame pixel stats flag luma fades; scene-duration outliers flag speed ramps/pacing anomalies; beat grid from audio (librosa on downloaded audio or transcript-timed proxy) flags cut-on-beat.
2. **VLM classification** via `scene.describe(prompt=...)` on candidate boundaries: structured prompt over multi-frame windows spanning each cut ("frames A1..A3 end shot A, B1..B3 start shot B — classify the transition: whip_pan | zoom_punch | match_cut | hard_cut | other; return JSON with confidence + evidence"). Windowed *across* boundaries is the key trick — motion techniques live at the cut, not inside a shot. Prompts iterated using the cookbook's `Prompt_Experiments_and_Benchmarking` pattern; `model_config`/sandbox escape hatch if the default VLM can't see motion.
3. **Validators**: confidence thresholds + rule checks (e.g. whip pan requires directional blur in *both* shots' boundary frames). Precision over recall — on stage, a wrong clip is worse than a missed one.

**Stage D — Index writing.** Detections become VideoDB scene indexes:
- Named index `"techniques"`: one Scene per detection window, `description` = generated natural-language description, `metadata` = `{technique, confidence, cut_time, shot_a_len, shot_b_len, ...}` → filterable via `query()`, countable via `aggregate()`.
- Named index `"content"`: plain VLM description per shot (what's on screen — enables "match cuts in *sneaker ads*").
- `index_spoken_words()` for dialogue-based queries later.
- Everything mirrored into SQLite (our catalog is source of truth for UI; VideoDB indexes are the search/stream engine).

**Stage E — Assets.** `generate_thumbnail(time=cut_time)` per detection for the grid; pre-warm `generate_stream(timeline=[(t-1.5, t+1.5)])` clip URLs (regenerate on demand — HLS URLs expire ~24h).

## 4. Query layer

- **Technique queries** ("every whip pan"): exact — SQLite/`query()` filter on `metadata.technique`. No semantic fuzziness for the core demo path.
- **Compound queries** ("match cuts in sneaker ads"): technique filter ∩ semantic search on `"content"` index (`coll.search(query, index_type=scene, index_id=content_index)`).
- **Open queries** ("which videos cut on the beat?"): answered from pacing analytics tables.
- **Query parsing**: small LLM call (`collection.generate_text(response_type="json")` or Claude) maps plain language → `{techniques[], content_terms, filters}`. `video.clip(prompt, content_type="visual")` kept as a fallback/baseline.
- Every result = `{video_id, start, end, technique, confidence, thumbnail, stream_url, recipe_id}` — playable exact moment.

## 5. Replication recipes

Generated once per detection at index time (LLM: technique definition + scene descriptions + timing data → structured recipe), cached in SQLite:

```json
{
  "technique": "whip_pan",
  "what": "...",
  "construction": {"camera": "...", "cut_point": "...", "easing": "..."},
  "steps": {"premiere": [...], "resolve": [...], "capcut": [...]},
  "clip_evidence": {"video_id": "...", "start": 12.4, "end": 14.1}
}
```

Per-technique base recipes are hand-curated (8 techniques = tractable); the LLM specializes them with the actual clip's parameters (shot lengths, motion direction, subject). Structured JSON output = consumable by other tools/agents (stated product goal).

**Remotion recipes**: each recipe also ships a `remotion` block — a paste-ready React/Remotion snippet + an AI-assistant prompt to recreate the technique programmatically (see [recipes/whip-pan.md](recipes/whip-pan.md) for the template). Differentiator for creator-dev audiences.

## 5b. Library source: eyecannndy.com

eyecannndy.com is a curated 135-technique library (whip-pan: 52 clips, match-cut: 83, speed-ramping: 53, split-screen: 118…) where **every clip links its Original Source on YouTube** plus full credits. Their clips are GIF loops (silent, copyrighted, fair-use-only) — we don't touch those. Instead:

1. Scrape technique → clip → **YouTube source link** mappings (real browser needed for pages; `clip_info_g` HTMX endpoint has the metadata).
2. Ingest the original ads/music videos into VideoDB — this *is* the reference library (right content type: ads + MVs).
3. Each video arrives with a weak label ("contains ≥1 <technique>") → calibration + recall measurement for M1, and demo-ready compound queries ("match cuts in ads").
4. Their taxonomy aligns our vocabulary (zoom punch = their crash-zoom; luma fade / J-L cuts / cut-on-beat have no visual-GIF category — ours to own).

## 6. Study reels

- v1: `SearchResult.compile()` or `video.generate_stream(timeline=[...])`-style stitch via legacy Timeline `add_inline` across videos → instant HLS reel.
- v2: `videodb.editor` Timeline — title card (`TextAsset`), per-clip technique label overlays, `Transition(in_/out)`, optional music bed (`AudioAsset` / `generate_music`), `CaptionAsset` animations. `download_stream()` → MP4 for offline/social. `reframe(target="vertical")` for 9:16 versions.
- Reel spec (ordered clip list + overlays) stored in SQLite so reels are reproducible/editable.

## 7. Style profiles

Computed from SQLite (+ `aggregate()` server-side counts as cross-check), per video and per creator/brand:

```json
{
  "creator": "...",
  "videos": 12,
  "avg_cut_length_s": 1.8,
  "cut_length_histogram": [...],
  "technique_frequency": {"whip_pan": 14, "zoom_punch": 9, ...},
  "beat_sync_score": 0.72,
  "pacing_curve": [...],
  "signature": "LLM-written 3-sentence editing signature",
  "evidence_clips": [{...}]
}
```

Cheap to compute, high demo value, and mostly derived from Stage B timing data — works even where VLM detection is weakest.

## 8. Data model (SQLite)

```
videos(id, videodb_id, title, source_url, creator, brand, duration_s, uploaded_at, index_status)
shots(id, video_id, idx, start_s, end_s, duration_s, content_desc)
detections(id, video_id, shot_id, technique, confidence, window_start_s, window_end_s,
           evidence_json, videodb_scene_index_id, thumbnail_url, created_at)
recipes(id, detection_id, json, created_at)
reels(id, name, query, clip_order_json, stream_url, mp4_url, created_at)
profiles(id, scope, scope_key, json, computed_at)
pipeline_state(video_id, stage, status, attempts, last_error, updated_at)
```

## 9. Repo layout (target)

```
src/
├── videodb_client.py      # connection, retries, URL regeneration
├── ingest/                # stages A–E, resumable orchestrator
├── detect/                # technique detectors: filters.py, prompts.py, validators.py, beats.py
├── catalog/               # SQLite models + queries
├── recipes/
├── reels/
├── profiles/
└── api/                   # FastAPI app
web/                       # React + Vite + hls.js UI
scripts/                   # calibrate_threshold.py, ingest_library.py, eval_detection.py
docs/                      # PROJECT.md, ARCHITECTURE.md, LEARNINGS.md
```

## 10. Milestones

**M0 — Hands-on validation (first!).** Verify key + credits; upload 3 test videos; run shot extraction at 3 thresholds; eyeball scene frames; test `scene.describe` with a whip-pan prompt on a video with known whip pans; test `compile()` ordering and MP4 download. *Exit: LEARNINGS updated with real observed behavior; classic-vs-v2 API decision made.*

**M1 — Detection core.** Calibration set (~10 videos with hand-labeled techniques, ~50 labels); build Stage B+C for 3 techniques (whip pan, zoom punch, luma fade); measure precision/recall; iterate prompts. *Exit: ≥80% precision on calibration set.*

**M2 — Full pipeline + catalog.** All 8 techniques; stages A–E resumable; SQLite catalog; ingest ~30 videos.

**M3 — Query + API.** FastAPI: search, clip URLs, recipes, profiles. Query parser.

**M4 — UI.** Search → thumbnail grid → HLS player → recipe panel. Style profile page.

**M5 — Reels + polish.** Reel builder (editor Timeline, labels, MP4 export). Scale library to ~100 videos. Rehearse the 2-min demo path end-to-end.

**M6 — Repo/GitHub.** Push to the new GitHub account when provided; seed issues from open questions + stretch techniques.

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| VLM can't see motion techniques from frames | Multi-frame boundary windows (`frame_count=3`); cheap pixel-stat pre-filters; sandbox with open-weight VLM as escape hatch; vocabulary already scoped to boundary-visible techniques |
| False positives on stage | Precision-first validators; demo only pre-verified queries; confidence threshold slider |
| HLS URLs expire (~24h) | Never persist stream URLs as durable; regenerate on request in API layer |
| Indexing cost creep | Resumable pipeline (never redo a stage); cheap filters gate VLM calls; ~$60/full pass is acceptable but not repeatable carelessly |
| `compile()` ordering unknown | Verify in M0; editor Timeline is the guaranteed fallback |
| Classic vs v2 API drift | Decide in M0 after hands-on; isolate SDK usage in `videodb_client.py` |

## 12. Open questions (tracked as future GitHub issues)

1. `compile()` — clip ordering control?
2. v2 `query()/aggregate()` — usable with custom scene metadata today?
3. Beat detection: local librosa vs any VideoDB audio analysis?
4. Best `frame_count` / boundary-window shape per technique?
5. Reuse `videodb-player` (Vue) vs hls.js in React?
6. Director/skills integration as a chat surface — post-v1?
