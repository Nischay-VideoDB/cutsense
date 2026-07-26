# Recipe: Speed Ramp

**What it is.** A playback-speed change inside one continuous shot: the clip runs slow and snaps to fast, or barrels along and drops into slow motion, with no cut anywhere. The ramp is timed so the speed change lands on an action beat — the moment a foot hits the ground, a door slams, a bass drop arrives. Because the shot never cuts, the audience reads it as time bending rather than as an edit.

**How it's constructed.**
- *Subject motion*: the shot needs a clear kinetic event to ramp around. A static frame ramped from 20% to 400% just looks like a glitch; a body in flight, a whip of the camera, or an object crossing frame gives the ramp something to describe.
- *Ramp point*: the transition should straddle the beat, not follow it. Typical shape is 6–10 frames of acceleration ending on the beat frame, then the new speed holds. The classic "slow to fast" is 30–40% speed, ramping over 8 frames to 200–300%.
- *Easing*: never step the speed. Use a smoothed retime curve — ease-out of the old speed, ease-in to the new — over 6–12 frames. A linear ramp reads mechanical; the S-curve reads like a camera operator's own acceleration.
- *Frame generation*: below about 50% speed you need interpolated frames. Optical flow looks best on clean, high-contrast motion with no occlusion; frame blending is the safe fallback when limbs cross, water splashes, or motion blur is heavy; nearest-frame (no interpolation) is the honest choice for stuttery, stylised looks.
- *Shutter considerations*: shoot high frame rate at a matching shutter — 120 fps at 1/250 gives you clean 25% slow motion with real per-frame blur. If you are speeding footage up, add synthetic motion blur (shutter angle 180–360) or the fast section will strobe. Conversely, slow motion from heavily blurred 24p footage will smear no matter which interpolation you pick.
- *Sweeteners*: pitch the audio with the ramp (or duck it and let music carry), push a 2–4 frame directional blur at the steepest part of the ramp, and add a light exposure lift on the slow section so it reads as the "held" moment.
- *Detector note*: our detector measures per-frame optical-flow magnitude within a single shot and flags monotonic velocity changes that exceed roughly 2x over fewer than 15 frames with no cut boundary present — that "no cut" condition is what separates a ramp from a hard speed cut.

## Remotion

Prompt to give an AI/code assistant:

> "In Remotion, build a speed ramp on a single video: play at 0.35x until frame N, then ramp over 8 frames to 2.5x and hold. Drive it by integrating the speed curve into a source-time value and feeding that to an OffthreadVideo via startFrom-style seeking, with an ease-in-out on the ramp. Add a directional blur that peaks at the steepest part of the ramp, and expose the speed values as props."

```tsx
import {
  AbsoluteFill,
  Easing,
  interpolate,
  OffthreadVideo,
  Sequence,
  useCurrentFrame,
} from 'remotion';

const RAMP_AT = 60;      // beat frame
const RAMP_LEN = 8;      // frames of acceleration
const SLOW = 0.35;
const FAST = 2.5;

// Instantaneous playback rate at a given output frame.
const speedAt = (f: number) =>
  interpolate(f, [RAMP_AT - RAMP_LEN, RAMP_AT], [SLOW, FAST], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.cubic),
  });

// Integrate the speed curve so source time stays continuous across the ramp.
const sourceFrameAt = (f: number) => {
  let acc = 0;
  for (let i = 0; i < f; i++) {
    acc += speedAt(i);
  }
  return acc;
};

export const SpeedRamp: React.FC<{src: string}> = ({src}) => {
  const f = useCurrentFrame();
  const sourceFrame = Math.round(sourceFrameAt(f));
  const speed = speedAt(f);

  // Blur tracks how fast we are moving through the source, capped for taste.
  const blur = interpolate(speed, [1, FAST], [0, 8], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <AbsoluteFill style={{filter: `blur(${blur}px)`}}>
        {/*
          One-frame Sequence offset by the current output frame: inside it the
          local frame is always 0, so `startFrom` alone decides which source
          frame is fetched. That gives exact per-frame seeking instead of
          leaning on playbackRate.
        */}
        <Sequence from={f} durationInFrames={1} layout="none">
          <OffthreadVideo
            src={src}
            startFrom={sourceFrame}
            muted
            style={{width: '100%', height: '100%', objectFit: 'cover'}}
          />
        </Sequence>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
```

*(Remotion has no optical-flow interpolation: seeking below 1x repeats source frames rather than synthesising new ones, so a 0.35x section will look stepped unless the source was shot at high frame rate — conform a 120 fps file and the ramp comes out clean. The `blur()` here is a uniform gaussian standing in for directional motion blur; for a real smear on the fast section use an SVG `feGaussianBlur` with `stdDeviation="8 0"` oriented along the dominant motion. For long compositions, replace the loop in `sourceFrameAt` with a precomputed prefix-sum array so you are not integrating from zero on every frame.)*

## Premiere Pro

1. Shoot high frame rate. Interpret the clip first: right-click in the Project panel → **Modify → Interpret Footage → Assume this frame rate: 23.976** to conform 120 fps to base slow motion with real frames.
2. On the timeline clip, right-click the fx badge → **Time Remapping → Speed**. A rubber band appears across the clip.
3. Ctrl/Cmd-click the rubber band to add a speed keyframe on the beat frame. Drag the band down to 35% before it and up to 250% after it.
4. Drag the keyframe's two halves apart to create the ramp length — 8 frames is a good default — then drag the blue bezier handle to smooth it into an S-curve.
5. Right-click the clip → **Time Interpolation → Optical Flow**. Render the section (**Sequence → Render In to Out**) to actually see it; the program monitor lies at draft quality.
6. If optical flow tears on crossing limbs, switch that clip to **Frame Blending**, or split the clip and use flow only on the clean portion.
7. Add **Transform** on the fast section, uncheck "Use Composition's Shutter Angle", Shutter Angle 180, to keep the sped-up frames from strobing.
8. Audio: unlink and handle separately — either mute the ramped audio and let music carry the beat, or keep it and accept the pitch shift as an effect.

## DaVinci Resolve

1. Project Settings → **Frame Interpolation**: set Retime Process to **Optical Flow** and Motion Estimation to **Speed Warp** (Studio only) for the cleanest slow motion; **Enhanced Better** is the free-version equivalent.
2. Edit page: right-click the clip → **Retime Controls** (Ctrl/Cmd+R). Speed handles appear under the clip.
3. Right-click the clip → **Retime Curve**. Switch the curve from **Retime Frame** to **Retime Speed** — this is the graph you actually want to shape.
4. Add keyframes either side of the beat, set the left segment to 35% and the right to 250%, then select both keyframes and click the **Smooth** (bezier) button. Drag handles until the acceleration is spread over 8–10 frames.
5. Per-clip override: **Inspector → Retime and Scaling → Retime Process** if this shot needs different interpolation from the project default.
6. Fusion page for surgical work: **TimeSpeed** or **TimeStretcher** node with a keyframed spline gives you frame-accurate control that the Edit-page curve cannot, and lets you feed a **VectorMotionBlur** driven by the same speed value.
7. Colour page: a small Gain lift (about +0.05) on the slow section, keyframed on, sells the held moment.

## CapCut

1. Select the clip → **Speed → Curve → Custom**.
2. Drag the graph points: pull the early points down to about 0.3x, the later points up to 2.5x, keeping the transition spread over two or three points rather than one vertical step.
3. Place the steep part of the curve on the beat — the waveform under the timeline is your guide; use **Audio → Beats** to drop markers first.
4. Toggle **Smooth slow motion** (optical-flow interpolation) on if the motion is clean; turn it off if you see warping around hands or hair.
5. Turn on **Voice change → Off / normal pitch** or mute the clip audio so the ramp does not chipmunk the dialogue.
6. Optional: add **Effects → Blur → Motion** on the fast portion, trimmed to about 0.2s.

## Reference clips

Populated automatically from the library: every `technique=speed_ramp` detection, annotated with the measured velocity ratio, the ramp length in frames, and whether a cut was present (ramps with a cut inside get demoted). Also see eyecannndy.com/technique/speed-ramping for a curated set with credits.
