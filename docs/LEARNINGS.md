# LEARNINGS — VideoDB platform & CutSense experiments

> Running log. Newest entries at the bottom of each section. Log everything non-obvious here.

## 2026-07-25 — VideoDB core primitives (docs + SDK research pass 1)

### Connect / collections / upload
- `videodb.connect(api_key=...)` — or env var `VIDEODB_API_KEY`. Python 3.8+, `pip install videodb`.
- Collections: `conn.get_collection()` (default), `create_collection(name, description)`, `make_public()/make_private()`.
- Upload: `coll.upload(file_path=...)` or `upload(url=...)` — **YouTube URLs supported directly**. `media_type`: video | audio | image.

### Two API surfaces (important)
- **Classic** (cookbook/PyPI, stable): `index_spoken_words`, `index_scenes`, `SearchType`/`IndexType`.
- **Newer** (current docs): `video.understand(analyzers=[...])` → analyzers: `spoken_words`, `vlm`, `object_detection`, `ocr`, `brand_detection`, `activity_recognition`, `location_detection`; then `video.index(...)` + `video.semantic_search(...)` / `video.query(...)` with metadata filters and `IndexCapability: semantic|query|aggregate`.
- Both live in the same SDK. Decide which to standardize on after hands-on testing.

### Scene indexing — the core primitive for CutSense
```python
video.index_scenes(
    extraction_type=SceneExtractionType.shot_based,   # "shot" | "time" | "transcript"
    extraction_config={"threshold": 20, "frame_count": 1},
    prompt="...",            # custom vision prompt applied per scene
    name="...",              # multiple named indexes per video supported!
    scenes=None,             # OR bring-your-own annotated scenes
) -> scene_index_id
```
- **shot_based = camera-cut detection.** Scene boundaries ARE the edits. `threshold` (default 20, lower = more sensitive) tunes cut sensitivity. This gives us cut density/pacing stats for free from `get_scene_index()` timestamps alone, before any VLM.
- time_based: `{"time": 10, "select_frames": ["first"|"middle"|"last"]}`. `frame_count` and `select_frames` are mutually exclusive. Docs say time_based weak on static videos; shot_based recommended.
- Custom annotation pipeline (full control): `video.extract_scenes(...)` → `SceneCollection` → per-`Scene.describe(prompt=...)` or your own VLM over `frame.url`s → `video.index_scenes(scenes=..., name=...)`. **This is the path for technique detection** — multi-frame temporal prompts needed for motion techniques (whip pans, zooms, speed ramps).
- Lifecycle: `get_scene_index(id)` → `[{start, end, description}]`, `list_scene_index()`, `delete_scene_index(id)`. Index searchable ~5–10s after job completes (async).

### Search
- `video.search(...)` / `coll.search(...)` with `search_type` (semantic|keyword), `index_type` (spoken_word|scene), `index_id` (target a specific named scene index), `result_threshold` (default 5), `score_threshold` (default 0.2).
- **Keyword search is single-video only** — collection keyword search raises NotImplementedError. Semantic works on both.
- `SearchResult`: `.shots`, `.compile()` → one stitched stream URL (study reels!), `.play()`.
- `Shot`: `video_id, start, end, text, search_score, scene_index_id, stream_url, player_url`, `.generate_stream()`.

### Streaming / clips
- `video.generate_stream(timeline=[(0,10),(120,140)])` → instant HLS stream URL, arbitrary clip stitching, **no re-encode wait**. `player_url` = hosted player page.
- Exact-moment playable clips (the core demo asset) are free — no rendering pipeline needed.
- `video.add_subtitle(SubtitleStyle())` exists.

### Implications for CutSense
1. Shot-based scene index = cut boundaries = pacing metrics for free.
2. Multiple named indexes per video → keep parallel indexes: "content" vs "technique/cinematography vocabulary".
3. `extract_scenes` + custom VLM loop = the technique-detection workhorse (temporal multi-frame prompts).
4. Collection-level semantic search over scene index = library-wide technique query → Shots → playable clips.
5. `SearchResult.compile()` ≈ study reel in one call (verify ordering/control; else Timeline API).

### Open questions (to verify hands-on)
- [ ] Does `compile()` preserve/allow custom shot ordering? Fallback: Timeline API.
- [ ] MP4 export availability (for downloadable study reels) vs HLS-only.
- [ ] Cost/latency of custom-VLM describe loop over ~100 videos × N scenes.
- [ ] Newer `understand()` analyzers (activity_recognition, object_detection) — useful for techniques?
- [ ] Whether search over our controlled technique vocabulary is better served by `query()` with metadata filters than by semantic search.

## 2026-07-25 — VideoDB assembly, export, platform (research pass 2)

### Timeline API — two generations, prefer `videodb.editor`
- **Legacy** `videodb.timeline.Timeline` (prints deprecation warning): `add_inline(VideoAsset(asset_id, start, end))` sequential concat + `add_overlay(start, Audio/Image/TextAsset)`; `generate_stream()`; `get_embed_code()`. Legacy `AudioAsset` has fade_in/out (max 5s), `TextAsset` uses ffmpeg-drawtext-like `TextStyle`.
- **New** `videodb.editor`: Track/Clip model — `Timeline(conn)` (settable `.background`, `.resolution`), `Track(z_index)`, `track.add_clip(start, Clip(asset, duration, transition=Transition(in_, out, duration=0.5), effect, filter, scale, opacity, fit, position, offset))`. Assets: `VideoAsset(id, start=trim_point, volume, crop)`, Audio/Image/TextAsset (fonts, borders, shadows). `Filter: blur|greyscale|contrast|...`; `Fit: crop|cover|contain|none`.
- **Trimming vs timing**: asset `start` = trim within source; `add_clip(start, …)` = placement on timeline.
- **Caption Asset**: text synced to audio timestamps (auto-subtitles in compositions).

### Export — MP4 exists (not HLS-only!)
- Streams are HLS (`stream.videodb.io/.../*.m3u8`), URLs valid ~24h (regenerate by re-calling).
- **MP4**: async download jobs — `conn.download(stream_link, name)`, `video.download()`, `editor.Timeline.download_stream(stream_url)`; poll status; final link expires 24h. Billed $0.03/min (720p).

### Subtitles / thumbnails / transcode / reframe
- `video.add_subtitle(SubtitleStyle(...))` — burned-in, needs spoken-word index first. Rich styling (font, colors, outline, alignment, margins).
- `video.generate_thumbnail(time=...)` → Image at timestamp; `get_thumbnails()`. (Grid thumbnails for the search UI = free.)
- `conn.transcode(source, mode=economy|lightning, VideoConfig(resolution, quality, framerate, aspect_ratio, resize_mode))` — async.
- `video.reframe(target="vertical", mode=ReframeMode.smart)` — smart 9:16 reframe (social clips of techniques!).

### Cross-video stitching (study reels) — 3 native paths
1. Timeline (either gen) with assets from different video ids → one compiled stream → `conn.download()` for MP4.
2. `SearchResult.compile()` → single stream stitched from matching segments across the collection.
3. Per-video `generate_stream([(s,e),...])` supercuts.
- Music/VO overlay supported. **No local ffmpeg needed anywhere.**

### Pricing (we have credits; for reference)
- Scene processing $0.003/scene · transcription $0.01/min · search $1.50/1k queries · upload $0.09/GB · storage $0.03/GB/mo · streaming $0.07/GB · download $0.03/min · inline edit $0.004/min · LLM tokens $0.0016–0.00875/1K.
- Rough CutSense math: 100 videos × ~200 shots = ~20k scenes ≈ $60 of scene processing per full-library describe pass — fine on credits, but don't re-index carelessly.

### Async / jobs
- Nearly every heavy op takes `callback_url`; generation methods support `wait=True, poll_interval, timeout` or return `GenerationJob`. SDK poll max 500s.

### Director agent framework & extras
- **Director** (github.com/video-db/Director, hosted chat.videodb.io): reasoning engine + built-in agents (upload, search, editing, clip gen); custom-agent guide exists. Companion: videodb-chat (UI), videodb-player. Could power the "ask in plain language" chat surface or at least the player.
- "Agent Skills" offering: video perception skills for external agents.
- Gen AI extras: `generate_voice/music/sound_effect/image/video/text`, `dub_video`, voice clone. `conn.youtube_search()` exists (library bootstrap!).
- RTStream (live RTSP/RTMP + real-time indexing) — not needed for CutSense v1.
- docs.videodb.io/llms.txt = full docs page index, very useful.

## 2026-07-25 — github.com/video-db org inventory (research pass 3)

### Repos that matter for CutSense (of 43 public)
- **videodb-python** (pushed today) — core SDK. Modules: client, collection, video, scene, shot, search, timeline (legacy), editor (new, 1209-line multi-track NLE), index, understanding, rtstream, sandbox, capture, job.
- **videodb-cookbook** — 64 notebooks. Key ones for us:
  - `guides/scene-index/playground_scene_extraction.ipynb` — tune shot/time extraction params
  - `guides/scene-index/advanced_visual_search.ipynb` — custom scene boundaries + `scene.describe()` + index
  - `guides/scene-index/custom_annotations.ipynb` — bring-your-own Scene objects/metadata
  - `guides/multimodal/Prompt_Experiments_and_Benchmarking.ipynb` — iterate vision prompts, benchmark models
  - `quickstart/scene_level_metadata_indexing.ipynb` — metadata on scenes (technique tags!)
  - `editor/creative/chess_montage.ipynb` — montage build (study-reel pattern)
  - `editor/feature/*` (10 notebooks) — full new-Editor coverage incl. caption animations
  - `examples/Keyword_Search_Counter.ipynb` — counting pattern for analytics
- **Director** (1.4k★, but last push 2026-01) — agent framework. `prompt_clip.py` agent = reference impl for technique-search→reel (chunk docs → parallel LLM selection → clip timeline). Custom agents: subclass BaseAgent. Newer energy is in **skills** repo.
- **skills** (pushed today) — VideoDB Agent Skills for Claude Code/Cursor (`npx skills add video-db/skills`), needs SDK ≥0.5.0. Recommended agent-integration path now.
- **agent-toolkit** — MCP server (`uvx videodb-director-mcp --api-key=KEY`) + `videodb.io/llms.txt` / `llms-full.txt` for LLM context.
- **videodb-node** — TS SDK, near parity incl. new editor (README 404s; read src). Means our web backend could be Node if we want; Python still primary.
- **videodb-player** (Vue HLS player) + **videodb-chat** (Vue chat frontend) — reusable UI pieces.
- **PromptClip** (stale) — precursor to `video.clip()`.

### SDK gems discovered (beyond passes 1–2)
- **`video.clip(prompt, content_type="spoken"|"visual"|"multimodal", model_name="basic"|"pro"|"ultra") -> SearchResult`** — one-call prompt-to-clip. Could be a fast baseline for technique search before our custom index is built.
- `index_visuals(prompt, batch_config, name)` / `index_audio(prompt, ...)` — indexing v2.
- `collection.aggregate(index_name, filter, group_by, metric="count")` — server-side technique frequency counts (style profiles!). Plus `query()` with filters, `ask()`, `legacy_search(..., stitch, rerank)`.
- Scene-level `metadata` dict on scenes/indexes → filterable technique tags (better than free-text-only).
- **CaptionAsset animations**: box_highlight, color_highlight, reveal, karaoke, impact, supersize.
- `create_sandbox(...)` — managed GPU sandboxes to run open-weight VLMs (Qwen, RT-DETR...) via `model_name/model_config/sandbox_id` on `index_scenes`/`describe`. Escape hatch if hosted VLM can't detect motion techniques.
- `insert_video(video, timestamp)`, `smart_vertical_reframe()`, `translate_transcript()`.
- shot_based `threshold`: HIGHER = fewer splits (agent confirmed direction).
- Cached SDK sources + trees in scratchpad `vdb/` dir for further digging.

## 2026-07-26 — M0 hands-on validation (ALL PASSED)

Environment: Python 3.12 venv, videodb 0.5.1. Scripts in `scripts/m0_0*.py`. Test collection `cutsense-m0`. Account: shubham jaiswal's (credits account) — key works.

### Observed platform behavior
- **YouTube-URL upload works** and is fast; `video.length` in seconds (float).
- `conn.youtube_search()` works (SerpAPI-shaped results; noisy — extract `link`+`duration`; "short" duration filter still returns some mid-length).
- **Shot extraction**: 6s whip-pan clip → 5 shots, boundaries frame-accurate. 2-min mixed tutorial → 12–16 shots across thresholds 25/20/15 (talking-head sections = one long 43–57s shot, as expected). Threshold direction confirmed: higher = fewer shots. `frame_count=3` gives 3 frames/shot incl. first frame.
- **Scene-collection IDs are deterministic**: `st{threshold}m15f3` — re-extract with same params reuses.
- **KEY FINDING — whip-pan blur lands at the START of the following shot.** Cut detection splits at the whip: the blurred frames become the first frames of shot N+1. So detector = classify shot-start frames. Confirmed visually on both whip pans in test clip.
- **VLM classification via `scene.describe()`: 5/5 correct** with a structured JSON prompt (labels whip_pan/zoom_punch/luma_fade/hard_cut/unclear): both real whip pans caught at 0.96/0.98 confidence, hard cuts correctly rejected, and a 0.04s end-of-video black stub labeled luma_fade (right answer, filtered by a min-duration validator). Returns clean JSON when asked.
- **Custom Scene objects + metadata index**: `index_scenes(scenes=[Scene(..., metadata={...})], name="techniques")` works; `get_scene_index` returns records with `scene_metadata` — **but metadata values come back stringified** ("0.96" not 0.96) — keep types in SQLite, treat VideoDB metadata as tags.
- **Search back works**: video-level semantic search on scene index → exact shots (scores 0.68–0.77); collection-level too (scores a bit lower, 0.52–0.65 — score_threshold 0.2 default fine). `compile()` on results → stitched stream URL instantly.
- **SDK warns legacy search is deprecated** → Search V2 (`search()`, `semantic_search()`, `query()`, `aggregate()`, `ask()`) is the go-forward path. **API decision: use Search V2 for retrieval; scene extraction + describe + index_scenes for detection.**
- **Streams/export all instant**: `generate_stream(timeline=[(s,e)])` → m3u8 in ~1s; cross-video legacy Timeline reel works (deprecation warning → use `videodb.editor`); `conn.download(stream_url, name)` returned **status "done" synchronously** with a signed GCS URL; MP4 verified locally: 8.04s for a 2+2+4s reel ✓ (saved `data/m0/cutsense_m0_reel.mp4`).

### M0 exit criteria vs plan
- ✅ Key + credits verified · ✅ 3 videos uploaded · ✅ threshold sweep + frames eyeballed · ✅ whip-pan VLM test (better than hoped) · ✅ compile + MP4 download verified · ✅ API decision made (V2 retrieval, classic scene pipeline for detection).
- Detection risk (the 40%) is materially reduced: boundary-window classification works on first try with default VLM, no sandbox needed so far.
- Still open for M1: precision on *diverse* footage (tutorial talking-heads are easy); zoom punch / match cut prompts; beat detection approach; `query()`/`aggregate()` V2 on custom metadata (test whether our "techniques" index is V2-queryable or legacy-only).

## 2026-07-26 — M1 first run + eyecannndy.com research

### M1 detection pipeline, first real run (whip-pan tutorial, 2:07, 55 shots)
- Pipeline (`src/detect/`): shot extraction → classify shot-start windows via `scene.describe()` → validators (min 0.15s shot, conf thresholds) → SQLite (`data/cutsense.sqlite`).
- Result: 16 whip_pan detections (conf 0.94–0.99), 38 hard_cuts, 0 unclear. Detections cluster where the tutorial demos the move repeatedly (46–50s, 91–98s) — plausible structure.
- **Visual spot-check of 3 detections: 3/3 genuine full-frame directional blurs.** (Two frames include player UI icons — the tutorial screen-records an editor preview; blur is still real. Long-term: such UI chrome could confuse content descriptions, note for library curation.)
- Conservative prompt rules ("blurry subject on sharp background is NOT whip_pan", "prefer hard_cut") seem to hold precision; recall untested (need hand labels).

### eyecannndy.com — mapped (research pass 4)
- **135-technique taxonomy** at `/technique/<slug>`, community-curated, credits per clip. Clip counts: transition 318, zoom-in 264, split-screen 118, flash-cut 101, shaky-cam 92, quick-cuts 88, match-cut 83, glitch 62, speed-ramping 53, **whip-pan 52**, jump-cut 39. Sub-techniques as page anchors (`zoom-in#crash-zoom`, `whip-pan#yo-yo-whip`).
- Mapping to our vocab: whip_pan→`whip-pan` · zoom_punch→`zoom-in#crash-zoom` · match_cut→`match-cut` · speed_ramp→`speed-ramping` · shake→`shaky-cam` · glitch→`glitch` · split_screen→`split-screen`. **No luma-fade, no J/L-cut, no cut-on-beat categories** (site is silent GIFs — audio techniques can't exist there).
- **Clips are GIF/WebP loops, not MP4s** (grid GIF → full WebP → original GIF via `/downloads/` proxy on `asset.eyecannndy.com`; assets fetch without Cloudflare challenge, HTML pages need a real browser).
- **Each clip links its Original Source (YouTube)** + full credits (director/DOP/editor/colorist). HTMX fragment endpoint `GET /clip_info_g/<clip_id>/?type=technique&t_id=<id>` (header `HX-Request: true`) returns metadata incl. the YouTube link. No JSON API/sitemap.
- Licensing: fair-use educational library; they own nothing, no redistribution rights. **Strategy: don't touch their GIFs — harvest the Original Source YouTube links per technique and ingest the ORIGINAL ads/MVs into VideoDB.** That gives us (a) a real reference library with exactly the right content, (b) weak ground-truth labels ("this video contains ≥1 whip pan") for calibration/recall measurement, (c) their taxonomy names as vocabulary alignment.
- Clip sources are mostly music videos + brand ads — exactly CutSense's target content.

### eyecannndy harvest executed (in-app browser, Cloudflare passed)
- Scraper mechanics that work: load `/technique/<slug>` in a real browser, collect `hx-get` attrs from `.grid-item`s, fetch `clip_info_g` fragments same-origin with header `HX-Request: true`, parse first youtube/vimeo/instagram link = Original Source. ~10 fetches in parallel per chunk, no rate-limit issues.
- Harvested whip-pan (52 clips), match-cut (83), speed-ramping (53) → **`library/eyecannndy/manifest.json`: 84 unique source videos, 51 YouTube, 23 multi-technique.** Vimeo is the next-biggest source (~30) — test whether VideoDB `upload(url=)` accepts Vimeo.
- Best calibration videos (multi-technique, dense): Watchtower of Turkey (11 clips, 3 techniques), ASD - Legendär/Populär (7, 3), Pa Salieu - My Family (6, 3), Sports Direct Women's Euro (5, 2), Travis Scott FE!N (5, 2), Nike SB Don't Make Plans (5, 2).
- ~20 clips per technique have no source link (film scenes mostly) — grid GIF still viewable on their site for manual reference, we skip them.
- `library/` is git-tracked (JSON metadata only, no media). `data/` stays ignored.

### First real-music-video run (ASD - Legendär/Populär, 4:51, 170 shots)
- Full-video classify (~168 VLM describes) ran ~13 min serial → **M2 must parallelize describe calls** (threads; API has no explicit rate limit observed).
- Results: 152 hard_cut, 8 whip_pan accepted, 7 zoom_punch, 2 luma_fade accepted.
- Spot-check: whip @204.36s genuine (full-frame streaking); **whip @121.44s (conf 0.97) looks like a false positive** (mostly-sharp STOP sign frame — possibly a fast move that settled before the sampled frame, but the frame itself doesn't show whip blur). Real precision measurement needs hand labels (M1 exit criterion) — tutorial content was easy mode, music videos are the real distribution.

### Match-cut & speed-ramp detectors (built + smoke-tested)
- **Constraint: `Scene.describe()` requires a server-side scene id** — synthetic cross-boundary Scene objects can't be described. Fallback implemented in `src/detect/boundary.py`: `Frame.describe()` (frames have server ids) on A-last + B-first-sharp frames with a composition prompt, then `collection.generate_text(response_type="json")` judges match_cut from the two descriptions. 2 vision + 1 text call per cut — needs a cheap local pre-filter before library scale (perceptual-hash mid-similarity on frame URLs is the plan).
- `generate_text(response_type="json")` wraps the payload in an `"output"` key.
- Speed ramp: within-shot `Scene.describe()` with frame-spacing prompt works normally.
- Smoke test on whip-pan clip: correct — no false match cuts (whip pans in same location correctly = plain_cut; one 0.78 candidate rejected by 0.85 threshold), no false speed ramps.

## 2026-07-26 (later) — calibration batch + pixel-veto second gate

### Batch ingest & parallelism
- 8 eyecannndy-sourced videos ingested (`scripts/ingest_batch.py`), ~1400 shots total classified.
- **Parallelized `describe()` with ThreadPoolExecutor (8 workers): 4.6x speedup** (60s IKEA ad: 32 shots in 32s vs ~150s serial). No rate-limit errors observed at 8 concurrent.
- **Bug fixed: `extract_scenes()` raises `InvalidRequestError: Scenes with given configuration already exists with id st20m15f3`** instead of returning the existing collection — this killed an `--all` loop. `extract_shots()` now catches it and parses the id out of the message to reuse (also avoids paying for re-extraction). Scene-collection ids are deterministic: `st{threshold}m15f{frame_count}`.
- Data-quality catch: eyecannndy's source links for FILM clips often point to a video essay or trailer, not the film (Grand Budapest → "Wes Anderson's Production Design" essay). Weak labels from film entries are unreliable; ads/music videos are solid.
- Dedupe gap: the manual ASD upload had no `source_url`, so `ingest_batch` re-uploaded it. Deleted the dupe and backfilled. Ingest should match on source_url OR title.

### THE KEY M1 FINDING: the VLM alone is not precise enough — pixel veto added
- On real ad/music-video footage the VLM confidently mislabels sharp frames as whip pans (IKEA @6.4s conf **0.98**, ASD @121.4s conf **0.97**, tutorial @46.9s conf 0.98 — all visually verified sharp, no blur). Tutorial footage had hidden this: it was easy mode.
- Root cause: the classifier sees only one shot's frames and can't reliably separate a blurred SUBJECT (or dark/soft footage) from a genuine whole-frame camera whip.
- Solution: **deterministic pixel-stat second gate** (`src/detect/filters.py`, numpy+PIL, no extra API cost beyond 3 small image fetches per candidate). Metrics: Laplacian-variance sharpness, border sharpness, gradient directionality, luma.
- Calibration path mattered: absolute `border_sharpness`/`directionality` thresholds scored only 4/10 on labeled frames. The winning design is **content-normalized**: compare the shot's first frame to its sharpest later frame (a whip settles). Combined gate = `ratio >= 1.5 OR absolute sharpness <= 220` → **11/11 on the hand-labeled calibration set** (`scripts/m1_calibrate_filters.py`), including vetoing both known 0.97/0.98 false positives. Caveat: 11 cases is small; needs the full hand-labeled set to trust.
- Applied to the stored batch via `scripts/m1_revalidate.py` (re-gates without re-paying for VLM): **vetoed 13 of 73 candidates (7 whip_pan, 6 luma_fade)**, kept 60. Two randomly chosen vetoes were visually confirmed correct.
- Design rule adopted: rejections are stored as `rejected:<label>` with the reason, never silently dropped — keeps precision debuggable.
- luma_fade thresholds (luma <=40 or >=215) may be too strict — vetoed frames at luma 51–198 could be genuine partial dips. luma_fade is lower-priority than the visual transitions; revisit with labels.

### Weak eval status (`scripts/m1_eval.py`)
- whip_pan HIT on 5 of 6 whip-pan-labeled videos; the single miss is the mislabeled Wes Anderson essay.
- Eval now distinguishes `HIT` / `miss` (ran, found nothing) / `n/a` (detector not run) — earlier output made un-run detectors look like failures.
- Still blocking M1 exit: hand labels for cut-level precision/recall.

### Recipe format extension: Remotion
- Recipes gain a `remotion` block alongside premiere/resolve/capcut: a paste-ready code snippet + prompt showing how to recreate the technique programmatically. First example: docs/recipes/whip-pan.md.

### Decision input: classic vs v2 API
- Classic (`index_scenes` + `legacy_search`) is battle-tested in cookbook; v2 (`understand`/`index`/`query`/`aggregate`) gives structured records + filters + aggregation, which style profiles want. Plan: use scene extraction + custom describe (classic) for detection, index with metadata, and use `query`/`aggregate` where supported — verify hands-on in M1.
