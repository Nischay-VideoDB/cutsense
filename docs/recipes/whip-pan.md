# Recipe: Whip Pan

**What it is.** A transition that hides a cut inside fast camera motion: shot A ends with the camera whipping (usually horizontally) into full-frame motion blur; the cut lands mid-blur; shot B opens with matching whip motion that decelerates into the new scene. The viewer's eye can't track through the blur, so the cut reads as one continuous move.

**How it's constructed.**
- *Camera motion*: whip at the END of shot A (accelerating out) and at the START of shot B (decelerating in), same direction.
- *Cut point*: inside the blur, typically 2–4 frames from peak velocity. Our detector finds exactly this: the blurred frames land at the start of shot B.
- *Easing*: motion accelerates hard out of A (ease-in) and decelerates into B (ease-out) — the two halves read as one swing.
- *Sweeteners*: directional blur boost at the seam, a whoosh SFX, ±5–10° rotation for energy.

**Effect spec** ([what these slots mean](_prompt-kit.md))

| slot | value |
|---|---|
| trigger | the cut, mid-blur — 2–4 frames past peak camera velocity |
| property delta | outgoing `x 0→−110%`; incoming `x +110%→0`; directional blur `0→40px→0`, peaking at the seam |
| duration | 8 frames total (4 out, 4 in) at 30fps |
| easing | out: `Easing.in(Easing.cubic)` · in: `Easing.out(Easing.cubic)` — one continuous swing |
| offset | blur peaks exactly on the cut frame, not before it |
| exit policy | the whip is the exit; the incoming shot plays clean once settled |

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

## Programmable editing (VideoDB)

**Can VideoDB author this?** Partly. The editor API has named transitions but no
keyframed motion or directional blur, so `Transition(in_="shuffle", out="shuffle")` gives
you the *slide* of a whip without the smear that sells it. Use it for a rough assembly;
use Remotion when the blur matters.

```python
from videodb.editor import Clip, Transition, VideoAsset
Clip(asset=VideoAsset(id=video_id, start=cut_time - 1.0), duration=2.0,
     transition=Transition(in_="shuffle", out=None, duration=0.3))
```

Assembly is what the editor API is genuinely good at: cutting, placing, layering,
static filters, named transitions and burned captions, with no local ffmpeg and no
render wait. Authoring *motion* — keyframed scale, directional blur, rate curves — is
not in the API; that is what the Remotion section above is for.

```python
# a study reel of every instance of this technique in the library
from videodb.editor import Timeline, Track, Clip, VideoAsset

timeline = Timeline(conn)
track = Track(z_index=0)
cursor = 0.0
for d in detections:                       # our detections, each with a video + window
    duration = round(d["window_end_s"] - d["window_start_s"], 3)
    track.add_clip(cursor, Clip(
        asset=VideoAsset(id=d["videodb_id"], start=d["window_start_s"]),
        duration=duration,
    ))
    cursor += duration
timeline.add_track(track)
stream_url = timeline.generate_stream()    # HLS, instantly playable
mp4 = timeline.download_stream(stream_url) # optional MP4 export
```

Two constraints worth knowing: a clip's out-point is `asset.start + clip.duration`
(there is no `end`), and a timeline serialising past ~100KB is uploaded as a URL — so
a few hundred clips is the practical ceiling for one reel.

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

## Reference clips

Populated automatically from the library: every `technique=whip_pan` detection, e.g. the classroom example video (cuts at 1.4s and 3.56s) and 16 moments in the in-camera tutorial. Also see eyecannndy.com/technique/whip-pan (52 curated examples with credits).
