# Recipe: Graphic Match

**What it is.** A cut inside a single scene where a distinctive shape, silhouette, screen position or piece of framing geometry is deliberately echoed across the seam. Wide shot of a round table cutting to a close-up of a round plate on that same table; a doorway arch in the master matched by the curve of a lamp in the reverse; two coverage angles cut so both subjects' heads land on the same third. The audience does not register a jump — the room never changed — so the effect is rhythmic and compositional rather than conceptual.

**How it differs from a match cut.** Same mechanic, different job. A **match cut** uses the shape to carry the viewer across a change of scene, subject, time or place — the shape is a bridge over a discontinuity. A **graphic match** stays inside the same scene and location, so there is no discontinuity to bridge: the echoed shape is there to make the cutting feel composed, to keep the eye anchored while the angle changes, or to build a visual motif within the sequence. If you can describe the cut as "we went somewhere else", it is a match cut. If the answer is "we're still in the kitchen, just closer", it is a graphic match.

**How it's constructed.**
- *Camera/subject motion*: usually static-to-static, or two moves travelling the same direction. Both shots come from the same setup or the same lighting continuity, so exposure, white balance and lens character already agree — the only thing you are engineering is the geometry.
- *Cut point*: at the frame where the two compositions overlap most tightly. Because the location is shared, you can also cut on a moment where a prop or body part sits in the identical screen position in both angles.
- *Easing*: hard cut. Graphic matches are also where a 2–4 frame dissolve is genuinely useful for smoothing very similar frames — anything longer starts to look like a mistake, because the viewer knows nothing changed.
- *Sweeteners*: keep the matched shape within about 5% of its screen size and 2% of its screen position across the cut; hold the horizon line or a strong vertical at the same coordinate; keep the dominant colour block on the same side of frame. Do not add whooshes or impacts — this is a quiet device.
- *Detector note*: our detector runs the same edge-map and shape-descriptor overlap it uses for match cuts, then requires the *opposite* verdict on the scene test — colour histogram, background classifier and audio ambience all consistent across the cut. High shape similarity plus same-scene continuity files as `graphic_match`; high shape similarity plus a scene change files as `match_cut`.

## Remotion

Prompt to give an AI/code assistant:

> "In Remotion, build a graphic match at frame N between two angles of the same scene: cut hard from AngleA to AngleB, apply a small measured alignment transform to AngleB (a few percent scale, a few pixels of offset) that holds through the cut and does not animate away, and optionally cross-dissolve over 3 frames. Include a debug mode that renders both angles with difference blending so I can tune the alignment values."

```tsx
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';

const CUT_AT = 84;
const DISSOLVE = 3;      // frames; 0 for a pure hard cut

type Align = {scale: number; x: number; y: number};

export const GraphicMatch: React.FC<{
  A: React.FC;
  B: React.FC;
  align?: Align;         // measured so B's shape sits on A's
  debug?: boolean;       // difference-blend both angles to tune `align`
}> = ({A, B, align = {scale: 1.03, x: -6, y: 4}, debug = false}) => {
  const f = useCurrentFrame();
  const t = f - CUT_AT;

  const transform = `translate(${align.x}px, ${align.y}px) scale(${align.scale})`;

  if (debug) {
    return (
      <AbsoluteFill style={{overflow: 'hidden', backgroundColor: 'black'}}>
        <AbsoluteFill>
          <A />
        </AbsoluteFill>
        <AbsoluteFill style={{transform, mixBlendMode: 'difference'}}>
          <B />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  const opacityB = DISSOLVE
    ? interpolate(t, [0, DISSOLVE], [0, 1], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
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
        <AbsoluteFill style={{transform, opacity: opacityB}}>
          <B />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
```

*(Unlike a match cut, the alignment offset here should stay put rather than relaxing to identity — the echoed geometry is the composition of shot B, not a temporary cheat, so animating it away undoes the match on the very next frames. Note also that `mixBlendMode: 'difference'` composites against the layers beneath it inside the same stacking context, so keep the debug mode's parent background black or the difference render will lie to you.)*

## Premiere Pro

1. Lay the two angles on V1/V2 with overlap. Set the top clip's **Opacity → Blend Mode → Difference** and step through both to find the frame pair where the echoed shape overlaps.
2. Nudge with **Motion → Scale** (1–5%) and **Position** (a few pixels) on the upper clip only. Resist bigger corrections: inside one scene, a large reframe reads as a cheat.
3. Turn blending off, cut with **Add Edit** on the best frame.
4. Optional micro-dissolve: **Constant Power**-free is fine here, just apply a **Cross Dissolve** and set Duration to 3 frames in the Effect Controls panel.
5. Check the seam with **Reference Monitor** in gang mode — put A's last frame in one viewer, B's first in the other, and confirm the shape and the horizon land on the same pixels.
6. Add a **Grid** effect at 1/3 spacing temporarily to verify the matched element sits on the same third in both shots, then disable it.

## DaVinci Resolve

1. Edit page: stack the angles, set the top clip **Composite Mode → Difference**, and align position and scale in **Inspector → Transform**.
2. Use the **Onion Skin** overlay in the trim tool (or a still grab from A with the wipe on) to confirm the shape overlap at the cut frame.
3. Colour page: because both shots share the scene, match them properly — one node grade copied across with **Shot Match** and then hand-corrected, so the echoed shape reads as the same object under the same light.
4. If a stray element in B breaks the echo, Fusion page: **Polygon** mask plus **Transform** to shift just that element a few pixels, tracked with a **Planar Tracker** if it moves.
5. Keep the ambience continuous — put the room tone on its own track spanning both clips rather than relying on the clips' own audio.

## CapCut

1. Import both angles, overlay the second on the first, set **Blend → Mode → Difference**.
2. Drag and pinch the overlay until the shared shape lines up, noting the Scale and Position values.
3. Reset blending, move the clip to the main track, and re-apply the Scale/Position you noted.
4. Split both clips so the cut lands on the aligned frame, with no transition (or a 0.1s **Dissolve** if the frames are nearly identical).
5. Leave one music/room-tone track running across the cut so the scene never breathes.

## Reference clips

Populated automatically from the library: every `technique=graphic_match` detection, with the shape-similarity score, the matched frame pair, and the same-scene confidence that separated it from `match_cut`. There is no eyecannndy category for graphic match — it folds these into their match-cut page — so the library's own detections are the reference set here; cross-check against eyecannndy.com/technique/match-cut only if you want the scene-changing cousin for contrast.
