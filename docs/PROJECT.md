# CutSense — Project Context

> Living context doc. Everything an engineer (or agent) needs to pick up this project cold.
> Platform learnings live in [LEARNINGS.md](LEARNINGS.md).

## One-liner

Every editing technique ever used in your reference library, searchable like a database. Ask for a technique, get playable clips of the exact moment and a recipe to replicate it.

## Problem

Editors learn by reverse-engineering other people's work: folders of reference videos, scrubbed by hand, held together by memory ("which ad had that whip-pan into product shot?"). The knowledge exists in the footage; there's no way to query it. Tutorials teach techniques in isolation — the real question is "show me this technique working in real content, then tell me how to do it."

## Who it's for

Video editors, motion designers, creator teams, agency post-production houses with reference libraries; editing educators building course material.

## Product surface (6 features)

1. **Ingest** — drop in ~100 real edited videos (ad breaks, music videos, creator content, trailers)
2. **Technique indexing** — index how each video is cut:
   - transitions: whip pan, luma fade, match cut, J/L cuts, speed ramps, zoom punches
   - effects: shake, glitch, overlays, split screens
   - pacing: cut frequency, rhythm to music
3. **Plain-language search** — "show me every whip-pan", "match cuts in sneaker ads", "which videos cut on the beat?" Results are playable clips of the exact 2-second moment, not full videos with timestamps.
4. **Replication recipes** — per result: what the technique is, how it's constructed (camera motion + cut point + easing), steps in Premiere/Resolve/CapCut terms
5. **Study reels** — "a study reel of every match cut in the library" → one stitched compilation
6. **Style profiles** — per-creator/brand editing signature: avg cut length, favorite transitions, pacing patterns, with clips as evidence. Structured JSON output so other tools/agents can consume.

## Demo story (2 min)

Open library of 100 videos → type "whip pan" → grid of exact-moment playable clips → click one, watch → open replication note → "make me a study reel of all of these" → play stitched reel → close with a creator style profile.

## Key risk & mitigation

**Technique detection is the hard part (~40% execution risk).** Mitigation = scope: nail 5–8 techniques reliably rather than promising every technique. A small vocabulary that always works beats a large one that misses on stage.

## Platform: VideoDB

- Docs: https://docs.videodb.io/ · SDK: `pip install videodb` · Org: https://github.com/video-db
- We have generous credits — use the platform maximally (scene indexing, semantic search, streams, timeline compilation, Director agents where useful).
- API key lives in `.env` (`VIDEO_DB_API_KEY`), gitignored. Key was shared in chat → rotate before demo.

## Working agreements

- **GitHub**: `github.com/falgunitripathi` — repo to be created there. **Ask for auth before the first push; never push without asking.** Issues/PRs tracked there.
- **Deploy**: Railway (Docker). See [HOSTING.md](../HOSTING.md).
- **VideoDB accounts**: primary = the project account (Falgunitripathi8) via `VIDEO_DB_API_KEY`; `VIDEO_DB_API_KEY_LEGACY` still holds the first calibration videos, and rows carry an `account` column so both can be served.
- **No AI attribution** anywhere: commits, comments, PRs.
- Reference videos and media never committed (gitignored under `data/`).

## Repo layout

```
cutsense/
├── docs/          # PROJECT.md (this file), LEARNINGS.md, architecture docs
├── src/           # application code
├── scripts/       # one-off ingest/index/experiment scripts
├── data/          # local media + caches (gitignored)
└── .env           # VIDEO_DB_API_KEY (gitignored)
```

## Status log

- **2026-07-27** — Library at **44 videos, all scanned: 6,715 shots classified → 558 accepted techniques** (281 whip pan, 164 zoom punch, 95 luma fade, 10 graphic match, 8 match cut). App live locally (API + eyecandy-style UI) and pushed to [github.com/falgunitripathi/cutsense](https://github.com/falgunitripathi/cutsense) (public). Open: graphic_match over-fires on ad footage (gated at 0.95, needs a v4 judge), speed_ramp still finds nothing, and M1 exit still needs hand labels.

- **2026-07-25** — Project kicked off. Repo scaffolded, git initialized (local only). Three deep-research passes over VideoDB docs + GitHub org; findings in LEARNINGS.md. Architecture plan written (ARCHITECTURE.md).
- **2026-07-26 (M1 in progress)** — Library sourced from eyecannndy.com (84 videos with weak technique labels); 8 calibration videos ingested and scanned (~1400 shots). Whip-pan detection hardened with a deterministic pixel-stat second gate after the VLM was caught producing 0.97–0.98-confidence false positives on real ad/music-video footage (gate: 11/11 on the hand-labeled set, vetoed 13 of 73 stored candidates). Match-cut judge rewritten to commit to intermediate facts — precision fixed, recall now the open problem. Content scene index + semantic search validated. Remaining for M1 exit: hand labels for cut-level precision/recall.
- **2026-07-26** — **M0 hands-on validation passed in full.** 3 test videos ingested; shot extraction calibrated; VLM whip-pan classification 5/5 correct at first attempt (0.96–0.98 conf); technique index + metadata + semantic search + compile() + MP4 export all verified end-to-end. API decision: Search V2 for retrieval, scene-extraction pipeline for detection. Detection risk sharply reduced. Next: M1 (calibration set + 3-technique detection core).
