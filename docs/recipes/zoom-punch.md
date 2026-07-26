# Recipe: Zoom Punch

**What it is.** An abrupt scale jump across a cut — also called a crash zoom or punch-in. Shot A is at 100%, shot B is the same or a related frame at 110–140%, and there is no transition between them: the size change happens in a single frame. Used to accent a beat, land a punchline, or shove attention onto a face or object. Stacked on repeat (three punches on three snare hits) it becomes a rhythm device rather than an emphasis device.

**How it's constructed.**
- *Subject motion*: none required. The punch is an optical move, not a camera move — the frame gets bigger, the subject stays put. Recentre the anchor point on the subject's eyes or the object of interest, otherwise the punch drifts.
- *Cut point*: on the transient. Line the cut to the exact frame of the kick, snare, or word onset — one frame late reads as sloppy, one frame early reads as anticipation.
- *Easing*: a hard punch has no easing at all (step, 1 frame). A "settled" punch scales past the target and eases back: 100 → 128 → 120 over 4–6 frames with an ease-out, which reads like a real lens racking to a stop.
- *Sweeteners*: 2–5 frames of radial/zoom blur on the incoming side, ±1–2° rotation, a 1-frame frame-hold before the punch to load the beat, impact SFX or a low sub hit.
- *Detector note*: our detector reads it as a scale discontinuity across a cut with a high inter-frame content match — the two shots are largely the same pixels, just at a different magnification. Ratios below ~1.08 get filtered out as reframes, not punches.

**Effect spec** ([what these slots mean](_prompt-kit.md))

| slot | value |
|---|---|
| trigger | the transient — the exact frame of the kick, snare or word onset |
| property delta | `scale 1 → 1.28 → 1.20` (overshoot then settle); radial blur `14px→0`; optional `rotate ±1.5°→0` |
| duration | 1 frame for a hard punch · 5–6 frames for a settled one |
| easing | `Easing.out(Easing.cubic)` on the settle; a hard punch has no easing at all |
| offset | none — one frame late reads sloppy, one frame early reads as anticipation |
| exit policy | none; the punched scale is the new normal until the next cut |

## Remotion

Prompt to give an AI/code assistant:

> "In Remotion, build a zoom punch at frame N between SceneA and SceneB: SceneA sits at scale 1, SceneB cuts in at scale 1.28 and eases back to 1.2 over 5 frames with an ease-out cubic, anchored on a configurable transform origin. Add a radial blur that starts at ~14px on the punch frame and decays to 0 over 3 frames, plus a 1.5° rotation that settles with the scale."

```tsx
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';

const PUNCH_AT = 60;     // cut frame
const SETTLE = 5;        // frames for the overshoot to relax
const OVERSHOOT = 1.28;
const TARGET = 1.2;

export const ZoomPunch: React.FC<{
  A: React.FC;
  B: React.FC;
  origin?: string;       // e.g. '50% 38%' to punch toward the eyes
}> = ({A, B, origin = '50% 42%'}) => {
  const f = useCurrentFrame();
  const t = f - PUNCH_AT;

  const scale = interpolate(t, [0, SETTLE], [OVERSHOOT, TARGET], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  const rotate = interpolate(t, [0, SETTLE], [1.5, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  const blur = interpolate(t, [0, 3], [14, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  if (t < 0) {
    return (
      <AbsoluteFill style={{overflow: 'hidden'}}>
        <A />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <AbsoluteFill
        style={{
          transform: `scale(${scale}) rotate(${rotate}deg)`,
          transformOrigin: origin,
          filter: `blur(${blur}px)`,
        }}
      >
        <B />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
```

*(CSS `blur()` is a uniform gaussian, not a true radial/zoom blur — the centre smears as much as the edges. For a real crash-zoom smear, stack 4–6 copies of the scene at scales stepping from `scale` to `scale * 1.04` with opacity `1/n`, which approximates a radial streak outward from the origin.)*

## Programmable editing (VideoDB)

**Can VideoDB author this?** No. `Clip.scale` is a static value, not an animatable
property, so a punch — which is a one-frame scale *step* — has no representation in the
editor API. Build it in Remotion. VideoDB's job here is assembly: stitching the punches
you have detected into something watchable.

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

1. Cut on the beat. Duplicate the clip end onto a second track if you want the punch to read against a held frame.
2. On the incoming clip, use **Effect Controls → Motion → Scale**: set 120 (start conservative; 110 for talking heads, 130–140 for objects and text).
3. Drag **Anchor Point** onto the subject so the punch grows toward the eyes rather than the frame centre.
4. For a settled punch, keyframe Scale 128 → 120 over 5 frames, right-click the second keyframe → **Ease In**, and pull the bezier handle flat.
5. Add **Transform** on the incoming side, uncheck "Use Composition's Shutter Angle", Shutter Angle 180–360, and keyframe Scale over 2 frames so the blur only exists at the seam. Or use **Directional Blur** at 0° radial substitute if you want it cheap.
6. Sweeten: **ZoomH**-style whoosh or a 40 Hz sub thump on the punch frame, gain around −8 dB so it sits under the music.

## DaVinci Resolve

1. Edit page: cut on the transient. Open **Inspector → Transform → Zoom** on the incoming clip, set 1.20, and move **Anchor Point** onto the subject.
2. For the settled version, enable keyframes on Zoom: 1.28 at the cut, 1.20 five frames later. Open the **Keyframe** panel, switch the Zoom curve to **Ease Out**, and drag the handle to about 70% for a snappier settle.
3. Motion blur at the seam: Fusion page → **Transform** node driving Size, then a **VectorMotionBlur** or a **DirectionalBlur** in Radial mode, Length ramped 0 → 0.02 → 0 across 3 frames.
4. If your source is 4K in a 1080 timeline, do the punch in **Edit Sizing** rather than Input Sizing so you keep true resolution up to 200%.
5. Repeat punches: copy the incoming clip's Transform, then **Paste Attributes** onto the other beat clips and vary Zoom by ±0.03 so the pattern does not feel mechanical.

## CapCut

1. Split the clip on the beat (tap the beat markers from **Audio → Beats → Auto-generate** to place the cut precisely).
2. Select the second half, open **Scale** and drag to 120%.
3. Optional settle: add a keyframe at the cut with Scale 128%, another 5 frames later at 120%.
4. Add **Effects → Video effects → Zoom Lens** or **Shake** on the incoming side, duration trimmed to about 0.15s.
5. Drop an impact sound from **Audio → Sound effects → Impact** exactly on the cut.

## Reference clips

Populated automatically from the library: every `technique=zoom_punch` detection, with the measured scale ratio and cut frame on each hit so you can sort by punch strength. Also see eyecannndy.com/technique/zoom-in#crash-zoom for curated crash-zoom examples with credits.
