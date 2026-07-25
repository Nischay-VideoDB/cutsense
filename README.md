# CutSense

**The searchable technique archive for video editors.**

Every editing technique ever used in your reference library, searchable like a database. Ask for a technique ("show me every whip-pan"), get playable clips of the exact moment plus a recipe to replicate it.

Built on [VideoDB](https://videodb.io) for ingestion, scene/shot indexing, semantic search, and clip streaming.

## What it does

1. **Ingest** a reference library (~100 real edited videos: ads, music videos, trailers, creator content)
2. **Technique indexing** — indexes *how* videos are cut: transitions (whip pan, match cut, luma fade, J/L cuts, speed ramps), effects, and pacing
3. **Plain-language search** — every result is a playable clip of the exact moment
4. **Replication recipes** — how each technique is constructed + steps to recreate in Premiere/Resolve/CapCut
5. **Study reels** — stitch every instance of a technique into one compilation
6. **Style profiles** — per-creator/brand editing signatures (cut length, transitions, pacing) as structured JSON

## Project docs

- [docs/PROJECT.md](docs/PROJECT.md) — full context: vision, scope, architecture decisions
- [docs/LEARNINGS.md](docs/LEARNINGS.md) — running log of VideoDB platform learnings & experiments

## Setup

```bash
cp .env.example .env   # add your VIDEO_DB_API_KEY
```

`.env` is gitignored — never commit keys.
