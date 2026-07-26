# Recipe: Luma Fade

**What it is.** A transition built out of brightness rather than opacity. In its simplest form it is a dip: shot A falls to black (or blows to white) over a handful of frames and shot B rises out of it. In its more interesting form it is a luminance-keyed dissolve — the incoming shot appears first in the brightest values of the outgoing shot (or the darkest, keyed the other way), so B seeps through highlights, rim light and specular hits before it fills the frame. Reads as light itself doing the cutting.

**How it's constructed.**
- *Source requirement*: the outgoing frame needs luminance separation. A flat, evenly exposed shot has nothing for the key to grab and the transition collapses into a plain dissolve. Look for strong rim light, a lamp in frame, a bright sky, a dark silhouette against a window.
- *Cut point*: the crossover — where A and B are both roughly half present — should land on the beat. That means the transition starts 4–8 frames early. A dip-to-black of 12 frames total puts its midpoint on frame 6.
- *Easing*: animate the luma **threshold**, not the opacity. Sweep it from 100 (only the very brightest pixels show B) down to 0 (B fills everything) with an ease-in-out over 10–16 frames. Softness/tolerance stays around 15–25% so the key edge is a gradient, not a stencil.
- *Direction*: keying on highlights (B emerges from the bright values) feels like a reveal or a flare-out. Keying on shadows (B emerges from the dark values) feels like an ink bleed or a dissolve into night. Pick per cut; do not mix directions inside one sequence.
- *Sweeteners*: 2–4 frames of exposure lift on A just before the crossover so the highlights bloom into the key, a touch of gaussian bloom or glow on the transition frames, and a short reverb tail or riser under the seam. Keep the audio crossing before the picture (J-cut, 4–6 frames) so the ear leads.
- *Detector note*: our detector tracks mean frame luminance across a cut and flags a monotonic excursion toward 0 or 255 followed by a recovery inside about 20 frames. It also checks whether the shot changed during the excursion — if the frame dips to black and comes back to the same shot, that is a flash or an exposure event, not a luma fade.

## Premiere Pro
1. Dip version: place a **Dip to Black** or **Dip to White** transition on the cut, then set Duration to 12 frames and drag the alignment so the midpoint sits on the beat.
2. Keyed version: stack A on V1 and B on V2 with a 14-frame overlap, and apply **Track Matte Key** on B set to use V1 as the matte, Composite Using **Matte Luma**.
3. Because Track Matte Key has no animatable threshold, put a **Levels** or **Lumetri Curves** adjustment on the matte source (a duplicate of A on V3 used as the matte track) and keyframe Input White / Input Black to sweep the key: white point 255 → 0 over 14 frames.
4. Alternative single-effect route: apply **Luma Key** to the top clip and keyframe **Threshold** 100% → 0% with **Cutoff** around 20%, then right-click both keyframes → **Ease In / Ease Out**.
5. Bloom the seam: **Gaussian Blur** on a duplicate of the transition frames, blend mode **Screen**, opacity keyframed 0 → 40 → 0 across the 14 frames.
6. Audio: J-cut B's bed 5 frames ahead of the picture crossover, and put a short riser under the transition at about −12 dB.

## DaVinci Resolve
1. Dip version: Edit page, drop **Dip to Color Dissolve** on the cut, set the colour to black or white in the Inspector, Duration 12 frames, and set the transition ease to **Ease In and Out**.
2. Keyed version: Fusion page is the right place. Bring both shots in as MediaIn nodes.
3. Add a **Luma Keyer** (or a **ColorCorrector** feeding a **Matte Control**) fed from shot A, and connect its output to the effect mask of shot B, so B is only visible where A is bright.
4. Keyframe the keyer's **Low** and **High** range so the visible band widens: High 1.0 → 0.0 over 14 frames, with 0.1–0.2 of softness on the range. Right-click the animated value → **Ease In and Out** in the Spline editor.
5. Composite with a **Merge** node, then add a **Glow** node after the Merge with Gain keyframed 0 → 1.5 → 0 across the transition for the bloom.
6. Back on the Edit page, use a **Fusion Transition** rather than a Fusion clip if you want the setup reusable across other cuts.
7. Colour page: on A's tail, a keyframed Lift/Gain push of about +0.08 gives the key something brighter to bite into.

## CapCut
1. Simple dip: place **Transitions → Basic → Fade to black** (or **Flash white**) on the cut, duration 0.4s.
2. Keyed look: **Transitions → Light** category — the glow and flare styles are luma-driven and land close to a proper luma fade on mobile.
3. Manual version: overlay B on top of A, set B's **Blend → Mode → Screen**, and keyframe B's opacity 0 → 100% over about 0.5s. Screen blending makes B appear in A's bright areas first, which is the same idea with less control.
4. Add **Effects → Video effects → Glow / Halo** trimmed to the transition length.
5. Bring the music or a riser in about 5 frames before the picture crossover.

## Remotion

Prompt to give an AI/code assistant:

> "In Remotion, build a luma fade between SceneA and SceneB over 14 frames centred on frame N. Render SceneB above SceneA and mask it with a luminance mask derived from SceneA, sweeping the mask threshold from 1.0 down to 0.0 with an ease-in-out so B emerges from A's brightest values first. Support a `direction` prop for keying on shadows instead, and add a bloom that peaks at the crossover. Also provide a simple dip-to-black mode."

```tsx
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';

const FADE_AT = 60;      // crossover frame (the beat)
const LEN = 14;          // total transition length

export const LumaFade: React.FC<{
  A: React.FC;
  B: React.FC;
  direction?: 'highlights' | 'shadows';
  mode?: 'keyed' | 'dip';
}> = ({A, B, direction = 'highlights', mode = 'keyed'}) => {
  const f = useCurrentFrame();
  const start = FADE_AT - LEN / 2;

  // 1 -> 0: at 1 only the very brightest pixels of A reveal B; at 0 B fills.
  const threshold = interpolate(f, [start, start + LEN], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.cubic),
  });

  const bloom = interpolate(f, [start, FADE_AT, start + LEN], [0, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  if (mode === 'dip') {
    // Two-stage dip: A out over the first half, B in over the second.
    const aOpacity = interpolate(f, [start, FADE_AT], [1, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.in(Easing.quad),
    });
    const bOpacity = interpolate(f, [FADE_AT, start + LEN], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.out(Easing.quad),
    });
    return (
      <AbsoluteFill style={{backgroundColor: 'black'}}>
        <AbsoluteFill style={{opacity: bOpacity}}>
          <B />
        </AbsoluteFill>
        <AbsoluteFill style={{opacity: aOpacity}}>
          <A />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  // Keyed mode: a luminance mask built from a second render of A. The transfer
  // table is regenerated every frame, which is what animates the key edge.
  const SOFTNESS = 0.18;
  const lo = threshold - SOFTNESS;
  const SAMPLES = 33;
  const table = Array.from({length: SAMPLES}, (_, i) => {
    const luma = i / (SAMPLES - 1);
    // Smoothstep from lo -> threshold; inverted when keying on shadows.
    const x = Math.min(1, Math.max(0, (luma - lo) / SOFTNESS));
    const s = x * x * (3 - 2 * x);
    return (direction === 'highlights' ? s : 1 - s).toFixed(4);
  }).join(' ');

  const LUMA_MATRIX = [
    '0.2126 0.7152 0.0722 0 0',
    '0.2126 0.7152 0.0722 0 0',
    '0.2126 0.7152 0.0722 0 0',
    '0 0 0 0 1',
  ].join(' ');

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <svg width={0} height={0} style={{position: 'absolute'}}>
        <defs>
          <filter id="lumaMatte" colorInterpolationFilters="sRGB">
            {/* Collapse to luminance, then remap so `threshold` is the edge. */}
            <feColorMatrix type="matrix" values={LUMA_MATRIX} />
            <feComponentTransfer>
              <feFuncR type="table" tableValues={table} />
              <feFuncG type="table" tableValues={table} />
              <feFuncB type="table" tableValues={table} />
            </feComponentTransfer>
          </filter>
          {/* SVG masks are luminance-based by default, so the grey matte above
              is read directly as the reveal. */}
          <mask id="lumaMask" maskUnits="objectBoundingBox">
            <foreignObject width="100%" height="100%">
              <div
                style={{width: '100%', height: '100%', filter: 'url(#lumaMatte)'}}
              >
                <A />
              </div>
            </foreignObject>
          </mask>
        </defs>
      </svg>

      <AbsoluteFill>
        <A />
      </AbsoluteFill>

      <AbsoluteFill
        style={{
          WebkitMaskImage: 'url(#lumaMask)',
          maskImage: 'url(#lumaMask)',
          filter: `brightness(${1 + bloom * 0.25})`,
        }}
      >
        <B />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
```

*(This works because Remotion re-renders the whole tree every frame, so the regenerated `tableValues` animate the key edge — but it costs you a second full render of scene A into a `foreignObject`, which roughly doubles the cost of the transition frames. `mask-image: url(#id)` also needs the `-webkit-` prefix in Chrome, which is what the renderer uses. If A is a video rather than a component, or you want a genuinely soft, gradeable key, do the composite in a shader instead — `mix(colorA, colorB, smoothstep(threshold - softness, threshold, luma(colorA)))` with `threshold` as a uniform — since sampling a video twice through an SVG filter chain gets expensive fast. The dip mode has none of these caveats and is exact as written.)*

## Reference clips
Populated automatically from the library: every `technique=luma_fade` detection, tagged with the luminance excursion direction (toward black or toward white), the excursion depth, and the transition length in frames. There is no eyecannndy category for luma fade — their transition pages cover whip pans, zooms and split-screen but not luminance-keyed dissolves — so the library's own detections are the reference set here.
