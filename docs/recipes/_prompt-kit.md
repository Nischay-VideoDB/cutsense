# Prompt kit — specifying a technique precisely enough to rebuild it

Every recipe in this folder leads with code, because that is what people try first. This
page is the shared vocabulary those sections use: the slots an effect description has to
fill, the house rules that keep a generated composition renderable, and the easing
inventory to pick from. Drawn from working motion-graphics pipelines, not invented here.

## The six-slot effect descriptor

An effect is under-specified until all six are answered. "Add a whip pan" is not a spec;
the table below is.

| slot | question | example |
|---|---|---|
| **trigger / anchor** | what moment does it fire on? | at the cut · at the cue word · at `pop - 0.05` |
| **property delta** | which properties move, from what to what? | `opacity 0→1` + `filter blur(18px)→blur(0)` · `scale 1.6→1` · `x +110%→0` |
| **duration** | how long? | 0.55s crossfade (16:9) · 0.4s (9:16) · 8 frames |
| **easing** | which curve? | `sine.inOut` · `power3.out` · `back.out(1.6)` · `spring({damping:12, stiffness:200})` |
| **offset from anchor** | does anything lag the trigger? | entrances start `cue + 0.25` · plate in at `start − 0.06` |
| **exit policy** | how does it leave? | the crossfade *is* the exit — no separate exit animation except on the final scene |

Write these six lines before writing any code, and a model can build the shot without
guessing. Leave one out and it will invent it.

## House rules for generated compositions

These are correctness constraints, not taste. Breaking them produces a composition that
looks right in a browser and fails when rendered headlessly.

- **Determinism.** No `Math.random()`, `Date.now()`, or `new Date()`. Seed any randomness
  (`Math.sin(seed * 9301 + 49297) * 233280` is a serviceable PRNG) so every render is
  identical.
- **Finite repeats.** `repeat: N`, never `repeat: -1`. Infinite loops break seek-based
  frame capture.
- **Frame-driven, not CSS-driven.** In Remotion every animation reads `useCurrentFrame()`;
  CSS transitions/animations and Tailwind animation classes do not render.
- **Animate only** opacity, transform, color and filter. Never `display`, `visibility`,
  or the width/height of a video element.
- **Crossfade, don't jump.** A hard swap between two full-frame states reads as a bug.
- **One accent colour** carries the energy. The urge to add a second colour is usually an
  urge to add motion.
- **No emoji** in rendered frames — many capture engines drop them. Use SVG or `✓ ✗ ★ →`.

## Easing inventory

Pick from these rather than inventing curves; they map cleanly between GSAP and Remotion.

| feel | GSAP | Remotion |
|---|---|---|
| crossfade, breathing | `sine.inOut` | `Easing.inOut(Easing.sin)` |
| exits | `power2.in` | `Easing.in(Easing.quad)` |
| headline / swipe entrance | `power3.out`, `expo.out` | `Easing.out(Easing.cubic)`, `spring({damping: 200})` |
| snappy UI pop | `back.out(1.4–1.7)` | `spring({damping: 20, stiffness: 200})` |
| bouncy | `elastic.out(1, 0.6)` | `spring({damping: 8})` |
| heavy settle | `power2.inOut` | `spring({damping: 30, stiffness: 40})` |
| typewriter, linear scrubs | `none` | `Easing.linear` |

## Two habits worth stealing

**Anchor to measured time, never estimated time.** If a technique lands on a word, a beat
or a cut, get the real timestamp and anchor to it. A visual landing a beat *after* its
trigger feels natural; landing before it feels broken.

**Never let a shot go static.** If something is on screen for more than ~3 seconds,
something in it should still be changing — a number counting, a meter filling, a slow
push-in. "Entrance then hold" is the failure mode that makes generated video look cheap.
