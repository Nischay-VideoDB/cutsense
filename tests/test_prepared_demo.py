"""Contract checks for the public, cache-only Vercel demo."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "showcase"


def _prepared_data() -> dict:
    result = subprocess.run(
        [
            "node",
            "-e",
            "global.window = {}; require(process.argv[1]); process.stdout.write(JSON.stringify(window.CUTSENSE_PREPARED_DATA));",
            str(SHOWCASE / "data.js"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_vercel_serves_only_the_static_prepared_app() -> None:
    config = json.loads((ROOT / "vercel.json").read_text())

    assert config["outputDirectory"] == "showcase"
    assert config["buildCommand"] == "true"
    assert config["installCommand"] == "true"
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/index.html"}]
    assert "functions" not in config


def test_prepared_data_is_traceable_to_the_catalog_snapshot() -> None:
    prepared = _prepared_data()
    snapshot = json.loads((ROOT / "library" / "catalog-snapshot.json").read_text())
    source_video_ids = {video["videodb_id"] for video in snapshot["videos"]}
    source_thumbnails = {thumbnail["thumbnail_url"] for thumbnail in snapshot["thumbnails"]}

    assert "46-video, 582-detection" in prepared["provenance"]["detail"]
    assert all(video["videoId"] in source_video_ids for video in prepared["videos"])
    assert all(clip["thumbnailUrl"] in source_thumbnails for clip in prepared["clips"])
    assert all("stream" not in clip for clip in prepared["clips"])


def test_public_assets_have_no_mutating_or_credentialed_surface() -> None:
    public_source = "\n".join(
        path.read_text() for path in SHOWCASE.glob("*") if path.is_file()
    )

    for forbidden in (
        "VIDEO_DB_API_KEY",
        "fetch(",
        "/api/",
        "type=\"file\"",
        "generate_stream",
        "collection.upload",
    ):
        assert forbidden not in public_source
    assert "Corresponding VideoDB clip unavailable in this demo." in public_source
    assert "Prepared study reel unavailable." in public_source


def test_key_spa_routes_render_from_static_data() -> None:
    harness = r'''
const path = process.argv[1];
const expected = process.argv[2];
const children = new Map();
const app = {
  innerHTML: "",
  focus() {},
  querySelector(selector) {
    if (!children.has(selector)) children.set(selector, { innerHTML: "", value: "", addEventListener() {}, querySelectorAll() { return []; } });
    return children.get(selector);
  },
  querySelectorAll() { return []; },
};
const nav = { setAttribute() {}, removeAttribute() {} };
global.window = { addEventListener() {} };
global.history = { pushState() {} };
global.location = { pathname: path };
global.document = {
  querySelector(selector) { return selector === "#app" ? app : nav; },
  querySelectorAll() { return []; },
  addEventListener() {},
};
require(process.argv[3]);
require(process.argv[4]);
if (!app.innerHTML.includes(expected)) throw new Error(`route ${path} did not render ${expected}`);
'''
    data_path = str(SHOWCASE / "data.js")
    app_path = str(SHOWCASE / "app.js")
    for path, expected in (
        ("/", "Prepared reports"),
        ("/library", "Moment library"),
        ("/video/federer", "18 retained technique detections"),
        ("/clip/federer-zoom-4348", "Corresponding VideoDB clip unavailable"),
    ):
        subprocess.run(
            ["node", "-e", harness, path, expected, data_path, app_path],
            check=True,
            capture_output=True,
            text=True,
        )
