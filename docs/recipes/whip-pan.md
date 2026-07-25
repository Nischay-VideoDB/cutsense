# Recipe: Whip Pan

**What it is.** A transition that hides a cut inside fast camera motion: shot A ends with the camera whipping (usually horizontally) into full-frame motion blur; the cut lands mid-blur; shot B opens with matching whip motion that decelerates into the new scene. The viewer's eye can't track through the blur, so the cut reads as one continuous move.

**How it's constructed.**
- *Camera motion*: whip at the END of shot A (accelerating out) and at the START of shot B (decelerating in), same direction.
- *Cut point*: inside the blur, typically 2–4 frames from peak velocity. Our detector finds exactly this: the blurred frames land at the start of shot B.
- *Easing*: motion accelerates hard out of A (ease-in) and decelerates into B (ease-out) — the two halves read as one swing.
- *Sweeteners*: directional blur boost at the seam, a whoosh SFX, ±5–10° rotation for energy.

## Premiere Pro
1. Shoot/select clips with real whips if possible (in-camera beats faked every time).
2. Cut A and B at peak blur. If no in-camera whip: add 4–6 frame overlap.
3. On the seam, apply **Transform** effect to both sides; keyframe Position X: A: 0 → −1500 over last 3 frames (ease-in, bezier), B: +1500 → 0 over first 3 frames (ease-out).
4. Uncheck "Use Composition's Shutter Angle", set Shutter Angle ≈ 360 for motion blur.
5. Add whoosh SFX centered on the cut.

## DaVinci Resolve
1. Edit page: cut at peak blur.
2. Effects → **Transform** on adjacent clip ends; keyframe Position X mirrored as above (Fusion page: Transform node + Vector Motion Blur for stronger smear).
3. Or drop the built-in **Push** transition, then add Motion Blur ≈ 1.0 in the transition inspector.

## CapCut
1. Split at the whip moment.
2. Transitions → **Pull in** / **Whip** style, duration 0.2–0.3s.
3. Or manual: keyframe Transform-X out of clip A and into clip B, add Blur → Directional at the seam.

## Remotion

Prompt to give an AI/code assistant:

> "In Remotion, build a whip-pan transition between SceneA and SceneB at frame N: over 8 frames, translate SceneA from 0 to -110% X with an easeIn, translate SceneB from +110% to 0 with an easeOut, cross them at frame N, and apply a horizontal directional blur that peaks (~40px) exactly at the seam. Add a subtle 3° rotation swing."

```tsx
import {AbsoluteFill, interpolate, Easing, useCurrentFrame} from 'remotion';

const WHIP_AT = 60;      // cut frame
const HALF = 4;          // frames per side

export const WhipPan: React.FC<{A: React.FC; B: React.FC}> = ({A, B}) => {
  const f = useCurrentFrame();
  const t = f - WHIP_AT;

  const xA = interpolate(t, [-HALF, 0], [0, -110], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic),
  });
  const xB = interpolate(t, [0, HALF], [110, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic),
  });
  // blur peaks at the seam, zero at the edges of the move
  const blur = interpolate(Math.abs(t), [0, HALF], [40, 0], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      {t < 0 && (
        <AbsoluteFill style={{transform: `translateX(${xA}%)`, filter: `blur(${blur}px)`}}>
          <A />
        </AbsoluteFill>
      )}
      {t >= 0 && (
        <AbsoluteFill style={{transform: `translateX(${xB}%)`, filter: `blur(${blur}px)`}}>
          <B />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
```

*(CSS `blur()` is radial; for a true directional smear use an SVG `feGaussianBlur` with `stdDeviation="40 0"` as the filter, or layer 3–5 offset copies with low opacity.)*

## Reference clips
Populated automatically from the library: every `technique=whip_pan` detection, e.g. the classroom example video (cuts at 1.4s and 3.56s) and 16 moments in the in-camera tutorial. Also see eyecannndy.com/technique/whip-pan (52 curated examples with credits).
