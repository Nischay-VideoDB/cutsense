/*
 * Prepared, read-only showcase data.
 *
 * Every video ID, detection, score, timestamp, evidence string, and thumbnail
 * URL below is copied from library/catalog-snapshot.json. The snapshot is the
 * tracked export of CutSense's VideoDB-backed technique catalog. It deliberately
 * contains no stream URLs: those are short-lived and regenerating one is paid work.
 */
window.CUTSENSE_PREPARED_DATA = {
  provenance: {
    label: "Prepared from the tracked VideoDB catalog snapshot",
    detail: "This public view reads a fixed showcase subset of the repository's 46-video, 582-detection snapshot. It does not issue VideoDB queries, upload media, or generate clips/reels.",
    source: "library/catalog-snapshot.json"
  },
  videos: [
    {
      slug: "federer",
      videoId: "m-z-019f9f75-b9b9-7093-a45f-da2c5c5f5c44",
      title: "סטטיק - פדרר (Prod. by Yinon Yahel)",
      creator: "סטטיק",
      sourceUrl: "https://www.youtube.com/watch?v=pQTkDVohdnc&t=1s",
      durationS: 140,
      techniqueTotal: 18,
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-b9b9-7093-a45f-da2c5c5f5c44-thumbnail-43.48/image",
      report: {
        headline: "18 retained technique detections across a 140.28-second edit, with fast, irregular cutting rather than a metronomic rhythm.",
        pacing: {
          cuts: 89,
          cutsPerMinute: 38.07,
          averageShotS: 1.58,
          fastCutShare: 46.1,
          rhythmic: false,
          curve: [5.99, 4.28, 6.84, 8.55, 7.7, 10.27, 4.28, 5.99, 6.84, 8.55, 3.42, 3.42]
        },
        techniqueSections: [
          { id: "luma_fade", label: "Luma Fade", count: 5, review: "5 independently confirmed" },
          { id: "zoom_punch", label: "Zoom Punch", count: 8, review: "8 independently confirmed" },
          { id: "whip_pan", label: "Whip Pan", count: 1, review: "retained; not independently re-judged" },
          { id: "speed_ramp", label: "Speed Ramp", count: 4, review: "retained; the historical audit window was not suitable for this technique" }
        ]
      }
    },
    {
      slug: "friesenjung",
      videoId: "m-z-019f9f75-72f1-73b1-89f4-9b6f12d6006f",
      title: "Joost, Ski Aggu & Otto Waalkes - Friesenjung (Official Video)",
      creator: "Joost, Ski Aggu & Otto Waalkes",
      sourceUrl: "https://www.youtube.com/watch?v=LMzAssOr2zE",
      durationS: 163,
      techniqueTotal: 13,
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-72f1-73b1-89f4-9b6f12d6006f-thumbnail-76.68/image"
    },
    {
      slug: "hotel-hennes",
      videoId: "m-z-019f9f8b-b6f2-7191-8063-8bdcf768913c",
      title: "WELCOME TO HÔTEL HENNES! GIGI HADID STARS IN H&M´S NEW FILM DIRECTED BY BARDIA ZEINALI",
      creator: "Not retained in the snapshot",
      sourceUrl: "https://www.youtube.com/watch?v=M0BX9J05tO0",
      durationS: 151,
      techniqueTotal: 12,
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f8b-b6f2-7191-8063-8bdcf768913c-thumbnail-50.48/image"
    }
  ],
  clips: [
    {
      id: "federer-luma-154", video: "federer", technique: "luma_fade", label: "Luma Fade", confidence: 0.99,
      startS: 13.9, endS: 16.9, cutS: 15.4, verified: "confirmed",
      evidence: "The shot starts almost completely white and then reveals the scene over the next frames.",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-b9b9-7093-a45f-da2c5c5f5c44-thumbnail-15.4/image"
    },
    {
      id: "federer-zoom-4348", video: "federer", technique: "zoom_punch", label: "Zoom Punch", confidence: 0.96,
      startS: 41.98, endS: 44.98, cutS: 43.48, verified: "confirmed",
      evidence: "The first frame is a strong radial blur/zoom that quickly resolves into the same tennis court composition.",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-b9b9-7093-a45f-da2c5c5f5c44-thumbnail-43.48/image"
    },
    {
      id: "federer-whip-6224", video: "federer", technique: "whip_pan", label: "Whip Pan", confidence: 0.95,
      startS: 60.74, endS: 63.74, cutS: 62.24, verified: "not independently re-judged",
      evidence: "The shot begins with strong full-frame directional motion blur that quickly settles into a sharp view.",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-b9b9-7093-a45f-da2c5c5f5c44-thumbnail-62.24/image"
    },
    {
      id: "federer-ramp-4200", video: "federer", technique: "speed_ramp", label: "Speed Ramp", confidence: 0.93,
      startS: 42, endS: 43, cutS: 42, verified: "audit window not suitable",
      evidence: "Several consecutive frames are nearly identical while an intermediate frame shows strong motion blur and a large positional jump, indicating a change in playback speed. [ratio 37.05]",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-b9b9-7093-a45f-da2c5c5f5c44-thumbnail-42.0/image"
    },
    {
      id: "friesenjung-whip-3876", video: "friesenjung", technique: "whip_pan", label: "Whip Pan", confidence: 0.9,
      startS: 37.26, endS: 40.26, cutS: 38.76, verified: "confirmed",
      evidence: "The first frame shows strong directional motion blur and high brightness across the entire image, which then resolves into a clear, sharp shot over the next frames.",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-72f1-73b1-89f4-9b6f12d6006f-thumbnail-38.76/image"
    },
    {
      id: "friesenjung-whip-7668", video: "friesenjung", technique: "whip_pan", label: "Whip Pan", confidence: 0.97,
      startS: 75.18, endS: 78.18, cutS: 76.68, verified: "confirmed",
      evidence: "The first frames have strong full-frame motion blur that quickly settles into a sharp image.",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f75-72f1-73b1-89f4-9b6f12d6006f-thumbnail-76.68/image"
    },
    {
      id: "hotel-whip-2880", video: "hotel-hennes", technique: "whip_pan", label: "Whip Pan", confidence: 0.96,
      startS: 27.3, endS: 30.3, cutS: 28.8, verified: "confirmed",
      evidence: "The first frames show strong full-frame directional motion blur as the view rapidly pans right before settling.",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f8b-b6f2-7191-8063-8bdcf768913c-thumbnail-28.8/image"
    },
    {
      id: "hotel-zoom-5648", video: "hotel-hennes", technique: "zoom_punch", label: "Zoom Punch", confidence: 0.92,
      startS: 54.98, endS: 57.98, cutS: 56.48, verified: "confirmed",
      evidence: "The first frame is a much wider view that abruptly jumps to a close-up over the next frames, consistent with a punch-in zoom.",
      thumbnailUrl: "https://storage.videodb.io/media/u-7c4327e8-15d7-4573-80f2-5f5726b36a19/img-m-z-019f9f8b-b6f2-7191-8063-8bdcf768913c-thumbnail-56.48/image"
    }
  ],
  recipes: {
    luma_fade: "Center the crossover on the beat. A dip generally needs 6-10 frames each way; a luma-keyed dissolve needs 12-20. Animate the luma threshold rather than opacity.",
    zoom_punch: "Cut on the transient. For a settled punch, overshoot from scale 1 to 1.28 and settle near 1.2 over 4-6 frames; keep the anchor on the subject.",
    whip_pan: "Cut at peak blur. If the move is not in-camera, overlap 4-6 frames and drive opposing horizontal transforms across the seam with directional blur.",
    speed_ramp: "Place the speed transition on the action beat. Use a 6-12 frame eased curve instead of a stepped rate change; interpolate source frames for deep slow motion."
  }
};
