# Recipe: Match Cut

**What it is.** A cut that changes scene, subject, time or place while deliberately carrying one visual or kinetic element across the seam: a shape, a composition, a gesture, a direction of travel. The bone tumbling in the air in *2001* becoming the orbiting spaceship; an eye dissolving into an iris; a hand reaching for a doorknob in one decade and pulling it open in another. The match is what buys the jump — the audience accepts a total change of context because one thing stayed put.

**How it's constructed.**
- *Camera/subject motion*: the matched element must occupy the same screen position and roughly the same scale on both sides. If it moves, the velocity vector should continue: something exiting frame left at 400 px/s in A should be travelling frame left at a similar rate in B.
- *Cut point*: at the moment of maximum similarity, not at the end of the action. Scrub both clips frame by frame, find the pair with the tightest overlap, and cut there — usually 1–3 frames earlier than instinct says.
- *Easing*: no transition. A match cut is a hard cut; adding a dissolve turns it into a different (softer, dreamier) device. The only exception is the classic eye-to-iris style match dissolve, 8–16 frames, where the shapes are close but not identical.
- *Sweeteners*: carry the audio across the seam (a sound that starts in A and finishes in B welds the two shots), match the dominant colour within ~10% so the eye reads continuity, and match the lens — a 24mm shape does not match a 85mm shape even when the outlines agree.
- *Detector note*: our detector scores cross-cut structural similarity — edge-map and shape-descriptor overlap on the frames either side of a cut — and then checks for a scene change (colour histogram, location classifier). High shape similarity plus a scene change is a match cut; high shape similarity with the same location is a graphic match, filed separately.

## Remotion

Prompt to give an AI/code assistant:

> "In Remotion, build a match cut at frame N: SceneA and SceneB each contain a matched shape at the same screen position. Cut hard on frame N with no transition, and apply a small alignment transform to SceneB — scale and rotation offsets that start at the matched values and relax to identity over 10 frames with an ease-out — so the shapes agree at the seam and B settles into its natural framing. Optionally support a short luminance-neutral cross dissolve for the eye-to-iris variant."

```tsx
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';

const CUT_AT = 72;
const SETTLE = 10;       // frames for B's alignment offset to relax
const DISSOLVE = 0;      // set to 12 for the match-dissolve variant

type Align = {scale: number; rotate: number; x: number; y: number};

export const MatchCut: React.FC<{
  A: React.FC;
  B: React.FC;
  align?: Align;         // offsets that make B's shape sit on A's at the cut
}> = ({A, B, align = {scale: 1.04, rotate: -2, x: 0, y: -8}}) => {
  const f = useCurrentFrame();
  const t = f - CUT_AT;

  const p = interpolate(t, [0, SETTLE], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  const scale = 1 + (align.scale - 1) * p;
  const rotate = align.rotate * p;
  const x = align.x * p;
  const y = align.y * p;

  const opacityB = DISSOLVE
    ? interpolate(t, [0, DISSOLVE], [0, 1], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
        easing: Easing.inOut(Easing.ease),
      })
    : 1;

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      {(t < 0 || opacityB < 1) && (
        <AbsoluteFill>
          <A />
        </AbsoluteFill>
      )}
      {t >= 0 && (
        <AbsoluteFill
          style={{
            opacity: opacityB,
            transform: `translate(${x}px, ${y}px) scale(${scale}) rotate(${rotate}deg)`,
          }}
        >
          <B />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
```

*(The alignment offsets are per-pair and have to be measured, not guessed: render both scenes at the cut frame, overlay them with `mix-blend-mode: difference` in a scratch composition, and tune `align` until the overlap goes black. Uniform scale and rotation can only get you so far — if the shapes disagree in perspective you need a real warp, which means an SVG `feDisplacementMap` or a WebGL layer rather than a CSS transform.)*

## Premiere Pro

1. Put A and B on stacked tracks V1/V2 with a generous overlap, and set the V2 clip **Opacity → Blend Mode → Difference** so you can visually align the shapes.
2. Nudge B in time (comma/period keys) and in space (**Motion → Position/Scale/Rotation**) until the difference render goes as dark as possible. Small corrections only — 1–4% scale, a few degrees.
3. Set the blend mode back to Normal, then trim so the cut lands on the tightest-match frame pair. Use **Add Edit** (Ctrl/Cmd+K) rather than a transition.
4. If the shapes need warping to agree, apply **Warp Stabilizer** or a **Corner Pin** on B's first 8 frames and keyframe back to identity by frame 8 so the correction disappears.
5. Weld the audio: extend A's ambience 6–10 frames past the cut, or start B's key sound 4 frames before the cut (J-cut) so the ear crosses first.

## DaVinci Resolve

1. Edit page: stack A and B, and use the **Composite → Composite Mode → Difference** on the upper clip to align shape and position by eye.
2. Refine with **Inspector → Transform** (Zoom, Position, Rotation) on B, then remove the composite mode and place the cut on the best frame.
3. Colour page: pull the two shots toward each other — match the dominant hue and the mid-grey level within about 10% — with a still grab from A as your reference wipe.
4. For a shape that needs to be bent into place, Fusion page: **Polygon** mask around the matched element in each shot plus a **Grid Warp** or **Corner Pin**, animated to identity over 8–12 frames.
5. For the match-dissolve variant, use a **Cross Dissolve** of 12 frames and set the transition curve to **Ease In and Out** so the midpoint holds longer on the ambiguous shape.

## CapCut

1. Import both clips and scrub each to the exact frame you want to match. Split off everything else.
2. Overlay B on top of A, set its **Blend → Mode → Difference** and lower opacity to align position and scale by dragging on the canvas.
3. Reset blending, then drag B down to the main track so it butts against A with no transition.
4. Fine-tune B's Scale and Rotate by 1–2 steps if the shapes are close but not aligned.
5. Keep one continuous sound across both — a single music bed or a sound effect that starts before the cut and ends after it.

## Reference clips

Populated automatically from the library: every `technique=match_cut` detection, tagged with the cross-cut similarity score and the frame pair the detector matched on, so you can sort strongest-match first. Also see eyecannndy.com/technique/match-cut for a curated set with credits.
