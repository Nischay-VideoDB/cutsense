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

### Decision input: classic vs v2 API
- Classic (`index_scenes` + `legacy_search`) is battle-tested in cookbook; v2 (`understand`/`index`/`query`/`aggregate`) gives structured records + filters + aggregation, which style profiles want. Plan: use scene extraction + custom describe (classic) for detection, index with metadata, and use `query`/`aggregate` where supported — verify hands-on in M1.
