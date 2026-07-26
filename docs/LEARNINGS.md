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

### Match-cut detector: v2 was badly over-firing, v3 fixed precision but recall is now the problem
- v2 (single free-text judgement) flagged **26 of 69 cuts** on the Cowboy Bebop teaser as match cuts. Its own evidence strings gave it away: "both shots keep a rooftop night fight…", i.e. it accepted *same-scene* cuts, which our definition explicitly excludes.
- **v3 fix — force the judge to commit to two intermediate booleans and derive the label in code**: `same_context` (same location/subject continuing?) and `composition_match` (a *named* specific carried element; generic "both dark/centered" doesn't count). Acceptance = `composition_match AND NOT same_context AND conf>=0.85 AND matched_element non-empty`.
- v3 result on the same teaser: **0 of 69** — distribution `(same_context, composition_match)`: (F,F) 51, (T,T) 9, (T,F) 8, (F,T) 1. Inspecting the 9 (T,T) blocks confirms they're genuinely same-scene (same rooftop fight, same title card, same western street) — v3 is right to reject them. The single (F,T) scored 0.73 and its evidence argued against itself ("dominant geometry changes"), so the confidence gate correctly held.
- So: v2 precision was terrible, v3 precision looks clean, but **recall on this video is 0 against eyecannndy's label that it contains a match cut**. Prime suspect: judging from *text descriptions* of two frames throws away the visual specifics a match cut is made of.
- Next experiments for match-cut recall (in priority order):
  1. `video.clip(prompt, content_type="visual", model_name="pro")` as a native baseline — one call, VLM sees pixels.
  2. Get both sides of a cut into ONE scene so the VLM sees both images: a second time_based scene collection whose windows straddle cuts, or a GPU sandbox VLM taking an image pair.
  3. Perceptual-hash structural similarity across the cut as a cheap candidate generator (also the planned cost pre-filter).
- Speed ramps: 0 of 43 shots on the same teaser — needs a video with known ramps (Usher/Travis Scott) before judging.

### Two bugs worth remembering
- **SQLite + ThreadPoolExecutor**: connections are single-thread by default; worker threads raised "SQLite objects created in a thread can only be used in that same thread", and because errors were caught per-item the run *looked* like it completed (0 detections in 0s) instead of crashing. Fixed with `check_same_thread=False` + a module-level `LOCK` around every statement in `catalog/db.py`. Lesson: per-item exception handling can disguise a total failure — watch the wall-clock, 0s for 69 API calls is the tell.
- Frame descriptions now cached in SQLite (`frame_descs`, keyed by frame id + prompt tag) so judge-prompt iteration costs nothing. Vision calls are the expensive part; never re-pay for them.

### Content scene index + search (product path validated)
- `index_scenes(extraction_type=shot_based, extraction_config={...}, prompt=<editor-oriented desc>, name="content")` on the Cowboy Bebop teaser: 70 records, **status `done` in ~15s** (much faster than expected), ~$0.21 of scene processing.
- Semantic search over it is genuinely good: "neon lit gunfight" → the three correct rooftop-fight shots (scores 0.49–0.56); "title card typography" → both title cards. This validates the compound-query path (technique filter from SQLite ∩ content semantic search = "match cuts in sneaker ads").
- Bonus: the content descriptions spontaneously mention transitions ("a quick, complex split-screen transition"), so the content index is *weakly* technique-searchable on its own — a useful fallback/second opinion for techniques our detectors miss.
- **`video.clip(prompt, content_type="visual")` requires an existing scene INDEX** (extracted scene collections are not enough — errors with "Scene index not found"). Even with the index it is slow: >10 min on a 2.5-min video (it LLM-processes the whole document set), so it is not a viable interactive path — fine as an offline second opinion only.

### Match-cut recall resolved: the detector was right, the test video was wrong
Three experiments, in order:
1. **`video.clip()` is a dead end.** Requires a scene index (not just extracted scenes), and even with one it **exceeds the SDK's hard 500s polling limit** (`RequestTimeoutError: Polling timed out after 500s`) on a 2.5-min video. Not viable interactively or offline. Ruled out.
2. **Paired vision** (`scripts/m1_exp_paired_vision.py`) — trick that works mechanically: extract a *second, time-based* scene collection (`time=2, frame_count=4`); windows that straddle a cut contain frames from both shots AND have real scene ids, so `describe()` lets the VLM see both sides as images. Verdict: **did not improve match-cut detection.** It agreed with the text judge on `same_context` but was much looser on `composition_match` (21 of 25 vs 9 of 69), rating ordinary continuity ("the man continues his movement") as a composition match. Keep the technique in the toolbox — it's the only way to get true cross-cut *vision* — but it needs a stricter prompt to be useful.
3. **Ground truth via a video with a famous match cut**: ingested the 2001: A Space Odyssey source. The v3 text judge found **4 of 57 cuts (7%, a plausible rate)**, including the Stargate eye matches, radiating light bursts, and a receding-figure match. **Visually verified the 162.2s detection: it is the iconic eye match** (identical iris composition, completely different color grade).

**Conclusion: the v3 judge is sound.** The Cowboy Bebop 0-detection result was a property of that footage, not a detector bug — two independent methods agree its cuts are same-scene. Lesson for eval: a weak label ("this video is in eyecannndy's match-cut category") is not a usable recall target; measure recall only against moments verifiable by eye.

### Taxonomy insight worth a product decision: `graphic_match`
Many curated "match cut" examples (and 9 of 69 Cowboy Bebop cuts our judge flagged as `same_context=true, composition_match=true`) are **graphic matches within one scene** — deliberately matched composition across a cut that stays in the same location. Our strict definition rejects these, which is why eyecannndy labels a video we score as 0.
Recommendation: ship **two labels** — `match_cut` (different context + matched composition; the classic) and `graphic_match` (same context + matched composition). Editors searching "match cut" get both, precisely labeled. Cost: near zero — the judge already commits to both booleans and every rejected row stores them in `raw_json`, so no re-running is needed. Use the text judge's stricter signal for `graphic_match`, not paired vision's.

## 2026-07-26 (app build) — API + UI standing up

### graphic_match shipped for free
Because the judge commits to `same_context` / `composition_match` and every rejected row keeps them in `raw_json`, adding the label was a pure local recompute (`scripts/relabel_boundaries.py`): **12 graphic matches recovered with zero API calls**, alongside 4 strict match cuts. Vocabulary is now whip_pan · zoom_punch · match_cut · graphic_match · speed_ramp · luma_fade.

### Account switch
New project key = a *different, empty* account (Falgunitripathi8); the first 10 calibration videos live in the earlier account. Rather than re-pay for detection, `videos.account` records which account holds each asset and `get_conn(account=...)` opens either — the UI serves both. Ingest dedupes per account.

### Asset economics learned the hard way
- First `/api/clips?limit=24` took **46s**: every card generated *both* a thumbnail and a stream. Streams are now deferred to hover (`/api/clips/{id}/stream`), thumbnails are fanned out 8-wide, and warm responses are **24ms**. `scripts/warm_assets.py` pre-generates thumbnails so a deploy is instant.
- Thumbnails are stable storage URLs (cache forever); only streams expire (refresh at 18h, inside VideoDB's ~24h window).

### Deploy shape (Railway)
Container filesystems are ephemeral, so a gitignored SQLite catalog means an empty library on every redeploy. Fix: `library/catalog-snapshot.json` is git-tracked, copied into the image, and `seed_if_empty()` loads it on boot. **Rule: a detection run that isn't exported to the snapshot does not exist in production.**

### Frontend notes
- hls.js first, native HLS only as fallback — Chromium's `canPlayType` says "maybe" for m3u8 then fails.
- `[hidden]` loses to any explicit `display` value; needed `[hidden] { display: none !important; }`.
- Grid thumbnails are lazy-loaded, so screenshots taken immediately after navigation show black cards — the images were fine, the timing wasn't. Verified with `naturalWidth` before believing the pixels.
- Canvas brightness sampling of VideoDB thumbnails is blocked (cross-origin `getImageData` SecurityError) — inspect frames by downloading them instead.
- Whip-pan thumbnails are generated at the cut, so the grid *shows the smear*: the technique is legible at a glance, which is the whole demo.

## 2026-07-27 — full-library ingest + detection pass

**Library: 44 videos (34 project account + 10 legacy), all scanned. 6,715 shots classified → 558 accepted techniques.**

| technique | accepted |
|---|---|
| whip_pan | 281 |
| zoom_punch | 164 |
| luma_fade | 95 |
| graphic_match | 10 |
| match_cut | 8 |

Rejections are kept, not dropped: 89 pixel-vetoed, 5,601 judge-rejected (mostly plain hard cuts).

### graphic_match over-fires at scale — gated, not fixed
The first sample of 12 looked fine; across the library the judge granted `composition_match` to **ordinary continuity cuts** — "both frames depict the same suburban house", "the same man in the same doorway", "the same living room sofa" — 9 of 32 cuts on a single IKEA ad, ~30 total at 0.86–0.92 confidence. That is not what an editor means by a graphic match. Root cause: because `graphic_match` permits the shots to stay in one scene, "matched composition" collapses into "the set is still on screen".
- **Stopgap applied**: separate thresholds — `match_cut` 0.85, `graphic_match` 0.95. Re-gated locally for free from stored judge output (252 candidates rejected, 10 kept).
- **Real fix (todo)**: a v4 judge field asserting the match is *deliberate and striking* — a distinctive shape carried across a change of angle/subject — rather than the scene merely persisting. Needs one re-run; frame descriptions are already cached so only the text judge repeats.
- Not uniform: ad-style footage floods, while music videos with genuinely distinct scenes returned none. Whatever gate we ship must be validated on ads specifically.

### match_cut doubled with the right footage
8 strict match cuts now (up from 4) after judging the videos whose library label suggests one. Consistent with the earlier finding: the detector is fine, it needs footage that actually contains the technique.

### Operational notes
- `--all` enumerates the collection once at start, so videos uploaded *during* a run are missed. Seven were skipped for exactly this reason; a second pass caught them. Not an error — worth knowing when interleaving ingest and detection.
- Detection throughput at 8 workers: roughly 1 shot/second (a 180-shot music video ≈ 140s). Boundary judging is ~2x slower per cut (2 vision + 1 text).
- Speed ramps: still 0 across the library. The within-shot detector runs and rejects; either the prompt is too strict or frame sampling (3 frames/shot) is too sparse to see velocity change. Next: sample more frames per shot on ramp-labeled videos.

### Four UI/serving fixes found by actually looking at the page
1. **Cross-account duplicates.** Several videos exist in both VideoDB accounts, so the same moment appeared twice. The API now hides a legacy video when a primary twin exists (same title or source URL): 558 stored detections → 475 shown across 35 videos.
2. **Display ranking.** Default ordering was confidence-first, which put luma fades (near-black frames) at the top and made the grid look empty. Ordering now follows `SHIPPING_TECHNIQUES` (whip pan first, luma fade last), confidence within a technique.
3. **Thumbnails proxied through our own origin** (`/api/thumb/{id}`). Third-party image hosts can be blocked by the embedding context, and same-origin also means cacheable (`max-age=86400`) and no VideoDB URLs leaked to the client.
4. **Static assets are versioned** (`/static/app.js?v=<mtime|commit-sha>`, `no-store` on the HTML). This one cost real time: the browser served a **cached app.js** for several iterations, so edits appeared to do nothing and the symptom looked exactly like a broken feature. Diagnosis was reading the live `src` attribute in the DOM and seeing the old URL. In production the same failure mode would serve stale JS after a deploy.

Related debugging lesson: `loading="lazy"` images never fetch when the page isn't being rendered/visible, so "0 of 60 loaded" is not evidence of a broken image pipeline. Confirm by probing with `new Image()` / `fetch()` from the page before changing anything.

## 2026-07-27 — Railway deploy

### Build failure and the fix
`pip install --no-cache-dir .` failed with `error: package directory 'src' does not exist`: the Dockerfile copied `pyproject.toml` and installed *before* `COPY src ./src`, and `[tool.setuptools] packages = ["src", ...]` needs the directory present. Reordering would fix it but would also rebuild dependencies on every code change.
Chosen fix: **don't install the package at all.** The app runs from the working directory (`uvicorn src.api.app:app`), so only dependencies are needed — `requirements.txt` in its own cached layer, then the source. Added `.dockerignore` (drops `.venv`, `data`, `scripts`, the eyecannndy manifests) to keep the context small.

### Thumbnails now ship in the snapshot
The snapshot carried videos + detections but not `clip_assets`, so a fresh container would have regenerated **555 thumbnails through the VideoDB API on first browse** — slow and billable. Thumbnails are stable URLs, so they now travel in the snapshot. The wrinkle: `clip_assets` keys on detection id, which is reassigned when seeding, so the export carries the natural key `(videodb_id, cut_time_s, technique)` and `seed_if_empty` remaps it (555/555 mapped).

### Verified the image layout without Docker
No Docker or Railway CLI on this machine, so the image was reproduced with file copies and booted **with `VIDEO_DB_API_KEY` deliberately unset**. Result: health, index, clips (21ms), thumbnails and recipes all work with no key at all — the deployed app reads cached results, exactly as intended. Only `/api/clips/{id}/stream` needs the key; it was returning a bare 500, now a `503 playback unavailable: VIDEO_DB_API_KEY is not set` via a `NotConfigured` exception.

### Networking note
`cutsense.railway.internal` is Railway's **private** service-to-service hostname — not browser-reachable and not SSH. Public access needs a generated domain on the service.

## 2026-07-27 — reframed around "analyse MY video"; the library became supporting cast

The browsable library answered the wrong question. The product is: **paste a video → what techniques does it use, and how do I rebuild them** — with the archive supplying the same technique in other people's work for comparison. Same detection engine, different centre of gravity.

Built: `POST /api/analyze` (threaded job, progress in SQLite, poll by id) → `GET /api/report/{video}` (techniques with exact moments, pacing, recipe per technique, related library clips) → a home screen that is a paste field, with the library behind a second tab.

Also closed the three missing brief features: plain-language `ask` (LLM parse → intent routing), study reels (`POST /api/reels`, cross-video timeline compile), style profiles (per creator/video, structured JSON + evidence clips), and pacing metrics (cut frequency, histogram, rhythm, pacing curve).

### THE BLOCKER: the Basic LLM tier's hackathon budget is spent
A fresh analysis returned **0 techniques across 88 cuts**. Cause: every `scene.describe()` was failing with
`You have reached the Hackathon budget for this model tier (Llm Basic). This tier has a $20 budget and needs at least $10 remaining to start. Used: $10.02; remaining: $9.98.`
- **Supported tiers are `mini, basic, pro, ultra`.** On the project account `mini`/`basic` are dead (they share the Basic budget) while **`pro` and `ultra` work**; the legacy account's `basic` still works.
- `pipeline.resolve_model()` now probes the chain `basic → pro → ultra` once per account with a live call, remembers the winner, and passes `model_name` on every describe. Re-running the same video with `pro`: **17 techniques found** (15 whip pan, 2 zoom punch) where the broken run reported zero.
- Budget state is invisible until a call fails — there is no `get_usage()` on the SDK Connection. Assume a tier can die mid-session.

### Two of my own bugs that made this worse
1. **I overwrote the model's evidence with the rejection reason** when storing a rejected detection, so 87 API failures all recorded as a bland `below_confidence` and the real error was unrecoverable from the database. Rejection reasons are now prefixed (`[reason] original evidence`), never substituted.
2. **A classifier that fails on every shot was reported as a successful analysis with no findings.** Now if every shot errored, the job is `failed` with the underlying message. Silent zeros are worse than loud failures.

### Smaller fixes
- Re-analysing a URL uploaded a *second* copy of the video (billed + stored). `analyze.run` now reuses an existing asset with the same `source_url` that already has shots.
- The plain-language parser routed "show me every whip pan" to `reel` because the phrasing sounds collective; a reel now requires an explicit reel word. A content filter matching nothing (e.g. "sneaker ads", which the library has none of) widens to the technique alone and says so, instead of returning an empty grid.
- Thumbnails get an `onerror` fallback so a failed image reads as empty rather than a broken-file icon.

## 2026-07-27 — speed ramp fixed, public gallery, persistence plan

### Speed ramp: the old detector could not have worked
It found zero across the whole library because it judged **3 stills per shot** — a change in playback speed is invisible in three frames. Replaced with a two-stage detector (`src/detect/motion.py`, `scripts/m2_speed_ramp.py`):
1. Extract a *dense* time-based collection (1s windows, 6 frames) and keep only windows sitting wholly **inside one shot**, so motion is comparable with no cut in the way.
2. Measure mean absolute pixel change between consecutive frames — a free, local motion series — then gate on it.
3. Ask the model only about survivors.

Gate design mattered more than the raw signal. `max/min` motion ratio alone surfaced whip pans, because a whip is a huge **one-frame spike**. A speed ramp is a *sustained* step, so the gate now needs `step_ratio >= 2.5` (slower half vs faster half) **and** `spike_share <= 0.62` (no single frame pair carrying the motion). On one ad that cut 41 windows → 5 candidates → 2 confirmed.

Result: **7 speed ramps across 5 videos**, with specific evidence ("frames 1-3 show minimal movement, while frames 4-6 show a sudden…"). Selectivity looks right, not enthusiastic: other videos returned 0 of 6, 1 of 9, 0 of 2.

### A regex bug worth remembering
Recovering an existing scene-collection id from the "already exists" error broke twice: `id (\S+?)\.?$` missed because the message has **trailing whitespace** after the period, and the unanchored fallback `id\s+(\S+)` matched the "id" inside **"Inval*id* request"**, parsing the id as `request:` and producing a baffling "does not exists" error. Now `\bid\s+(\S+)` with `.rstrip(". ")`, in one shared helper.

### Public gallery
`GET /api/gallery` returns every analysed video as a card — poster frame (its highest-confidence detection), technique tally with breakdown, cuts/min — and the home screen shows it under the paste field. Clicking a card opens that video's full report, so the archive doubles as a browsable public record of what has been analysed. Verified: 34 cards, 34/34 posters loading, click-through renders the report.

### Persistence
Visitor analyses are runtime rows, so they need storage outliving the container. `CUTSENSE_DB` now overrides the catalog path: mount a Railway volume at `/data` and set `CUTSENSE_DB=/data/cutsense.sqlite`. Postgres was considered and deferred — the catalog leans on SQLite-specific SQL (`INSERT OR IGNORE`, `COUNT(...) FILTER`, `datetime('now')`), so a volume buys durability without a dialect port.

**CLI blocker:** the Railway CLI is installed and logged in as `thelonelyrulershiv@gmail.com`, but that workspace does not contain the CutSense project id — only an unrelated project (whose services I deliberately left alone). Needs a login as the owning account, an invite, or `RAILWAY_TOKEN`.

### Thumbnails: two faults, neither one "broken URLs"
An audit of all 582 detections found **0 failing URLs**. The visible problem was:
- **11 detections had no thumbnail at all** — `generate_thumbnail` fails for some timestamps (a cut landing on the final frame, for instance) and a single attempt at the exact cut time leaves a hole.
- **~17 were near-solid-colour frames.** A 755-byte PNG is effectively a flat colour. That is *correct* for a luma fade (the frame really is black) but useless as a poster, and indistinguishable from a bug to anyone looking at the page.

Fixes:
1. `scripts/fix_thumbnails.py` — repairs missing/blank posters by trying neighbouring timestamps (±0.4s, ±0.8s, +1.2s) and keeping the frame with the most detail (grey-level std-dev), falling back to a frame image from the shot's scene collection, which already exists and costs nothing. **27 repaired; the re-audit reports 0 missing, 0 failing, 0 blank.**
2. `clips._make_thumbnail` retries offsets at generation time, so new analyses do not create holes.
3. Cheap audit trick: HEAD content-length is a fine blankness proxy, which turned a 571-image download into a fast pass.
4. Gallery posters are now ranked **by technique** before confidence — a luma fade is a near-blank frame by definition, so it made a poor card even at 1.00 confidence. Picking whip pan / zoom punch first transformed the gallery from rows of black rectangles into legible motion frames.

A whip pan's blur sits exactly at the cut and *is* the signal, so frames are only replaced when they carry almost no detail — never merely for being blurry.

### Railway auth: what I could and could not do
`railway login` needs a TTY (browser handoff or a pairing prompt); `--browserless` under a captured pipe produced no output and `script -q` cannot allocate a pty in this environment, so **the login has to be run in a real terminal**. The already-authenticated account's workspace does not contain the CutSense project — only an unrelated one, which I linked briefly to inspect and then unlinked without touching. `scripts/railway_setup.sh` now does the whole configuration (link → volume at `/data` → `CUTSENSE_DB` → deploy) idempotently once auth exists, either from `railway login` or a `RAILWAY_TOKEN` project token.

## 2026-07-27 — VideoDB deep dive (programmable editing · indexes/search · events · data model)

Verified page-by-page against the installed SDK (0.5.1). **Read the docs as markdown via `curl https://docs.videodb.io/<path>.md`** — WebFetch summarises and drops the code. `llms.txt` lists every page; `llms-full.txt` does not exist.

### Documented APIs that do not exist in 0.5.1 (would have cost us hours)
`ws.stream()` (it is `receive()`), `conn.get_event()`, `conn.delete_event()`, `index.delete_alert()`, `collection.index()`, `collection.list_videos()` (it is `get_videos()`). The `streams-and-exports` page teaches the **deprecated** timeline under the *new* import — `videodb.editor.Timeline` has no `add_inline`, and its `VideoAsset` has no `end`. Trust the SDK source over the editor docs.

### Programmable editing — what is actually true
- Current API is `videodb.editor`: `Timeline(conn)` (`.background`, `.resolution`) → `Track(z_index)` → `track.add_clip(start, Clip(asset, duration, transition, filter, scale, opacity, fit, position, offset, z_index))`. **Later `add_track()` renders on top.**
- Trimming vs timing are separate axes: `asset.start` indexes into the source; `add_clip(start=…)` places on the output; there is no `end` — the out point is `asset.start + clip.duration`.
- `Fit.none.value == "None"` (the *string*). Use `fit=None`.
- Timeline JSON over **100 KB** is auto-uploaded as a URL — roughly a few hundred clips, so long supercuts have a real ceiling.
- Editor `AudioAsset` has **no fade and no ducking** (the legacy asset did) — a regression to plan around for music beds.
- `CaptionAsset(src="auto")` needs `index_spoken_words()` first; animations: box_highlight, color_highlight, reveal, karaoke, impact, supersize.
- `generate_stream()` is a blocking POST — no job handle, no `callback_url`.

### Indexes & search v2 — the architecture we should be growing into
`understand(analyzers=[…])` → `index(source=analyzer, name=…, use_for=[semantic|query|aggregate], fields={semantic|filter|aggregate|sort: [...]})` → `semantic_search()` / `query(filter=…)` / `aggregate(group_by=…, metric=…)` / `ask()`.
- **`collection.index()` does not exist.** Collection-level grouping = giving per-video indexes the *same name* (and identical field structure, or the create 400s).
- A VLM analyzer can emit a **structured schema**, so our technique taxonomy could live in VideoDB as filterable/aggregatable fields instead of only in SQLite — `aggregate(group_by="technique")` would give style profiles server-side.
- Indexing is rows-first: `query`/`aggregate` work while an index is still `building`; only `semantic_search` needs `ready`.
- **Never mix v2 and legacy kwargs** — passing `index_id`/`search_type`/`result_threshold` silently downgrades the whole call to `legacy_search()`.
- `Index.field_schema[f].operators` is the runtime authority on which filters a field supports.

### Events are RTStream-only
`create_event`/`create_alert` hang off RTStream indexes; `videodb/video.py` has no alert methods at all. For uploaded video the only push is a one-shot `callback_url` on job completion. **So there is no "alert me when a technique appears" for VOD** — that has to be our own layer over `callback_url` + a query. Also: the two documented webhook payload shapes contradict each other (`event_id` vs `event_label`, ISO-8601 vs epoch-millis) — parse defensively.

### Data model
Video/Audio/Image carry **no metadata dict** — only name/description. The only filterable place to put session attributes is **index records**, where any non-reserved top-level key becomes queryable `data` (referenced without a `data.` prefix). An array of objects reports as `string_array`; nested dicts get no default field group and stay invisible until you declare a dotted path. `video.update()` changes the **name only**. `remove_storage()` drops bytes but keeps the record and its indexes searchable.

### Applied immediately: a reel bug this surfaced
Study reels 500'd with `video info not available for video_id: …`. Cause: a timeline can only reference assets belonging to the connection building it, and our library spans two accounts, so a mixed-account clip list is unbuildable. `build_reel` now groups by account, builds from the one holding the most clips, and **reports what it left out** ("3 clips from another account left out") instead of quietly shipping a shorter reel. Confirmed the modern editor path works: 5 clips / 15s across 4 videos, real HLS manifest, no legacy fallback.

### Recipe format extension: Remotion
- Recipes gain a `remotion` block alongside premiere/resolve/capcut: a paste-ready code snippet + prompt showing how to recreate the technique programmatically. First example: docs/recipes/whip-pan.md.

### Decision input: classic vs v2 API
- Classic (`index_scenes` + `legacy_search`) is battle-tested in cookbook; v2 (`understand`/`index`/`query`/`aggregate`) gives structured records + filters + aggregation, which style profiles want. Plan: use scene extraction + custom describe (classic) for detection, index with metadata, and use `query`/`aggregate` where supported — verify hands-on in M1.
