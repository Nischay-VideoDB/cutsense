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

## Pending research (in flight)
- Timeline/assets API, MP4 export, thumbnails, Director agent framework, limits/pricing — research pass 2.
- Full github.com/video-db org inventory (SDKs, cookbook examples, MCP server) — research pass 3.
