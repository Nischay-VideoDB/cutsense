"""The answer to "what did they do to this video, and how do I do it?".

One report per video: the techniques found with their exact moments, the pacing of
the edit, a recipe per technique, and — the reason the library exists — the same
technique working in other people's footage to compare against.
"""

from src.detect.prompts import SHIPPING_TECHNIQUES, TECHNIQUE_LABELS
from src.profiles import pacing

RELATED_PER_TECHNIQUE = 6


def _rows(db, sql, params):
    return [dict(r) for r in db.execute(sql, params)]


def build_report(db, videodb_id, read_recipe):
    video = db.execute("SELECT * FROM videos WHERE videodb_id=?", [videodb_id]).fetchone()
    if not video:
        return None

    shots = _rows(db, "SELECT start_s, end_s FROM shots WHERE videodb_id=? ORDER BY start_s",
                  [videodb_id])
    tech_marks = ",".join("?" * len(SHIPPING_TECHNIQUES))
    detections = _rows(
        db,
        "SELECT id, technique, confidence, cut_time_s, window_start_s, window_end_s, evidence"
        f" FROM detections WHERE videodb_id=? AND technique IN ({tech_marks})"
        " ORDER BY cut_time_s", [videodb_id, *SHIPPING_TECHNIQUES])

    by_technique = {}
    for d in detections:
        by_technique.setdefault(d["technique"], []).append(d)

    techniques = []
    for tech in SHIPPING_TECHNIQUES:          # stable, editor-friendly order
        found = by_technique.get(tech)
        if not found:
            continue
        related = _rows(
            db,
            "SELECT d.id, d.technique, d.confidence, d.cut_time_s, v.title, v.source_url"
            " FROM detections d JOIN videos v ON v.videodb_id = d.videodb_id"
            " WHERE d.technique=? AND d.videodb_id!=? ORDER BY d.confidence DESC LIMIT ?",
            [tech, videodb_id, RELATED_PER_TECHNIQUE])
        techniques.append({
            "technique": tech,
            "label": TECHNIQUE_LABELS.get(tech, tech),
            "count": len(found),
            "moments": [{"clip_id": d["id"], "cut_time_s": d["cut_time_s"],
                         "start_s": d["window_start_s"], "end_s": d["window_end_s"],
                         "confidence": d["confidence"], "evidence": d["evidence"]}
                        for d in found],
            "recipe": read_recipe(tech),
            "related_from_library": [{"clip_id": r["id"], "video_title": r["title"],
                                      "source_url": r["source_url"],
                                      "cut_time_s": r["cut_time_s"],
                                      "confidence": r["confidence"]} for r in related],
        })

    pacing_summary = pacing.summarise(shots) if shots else None
    return {
        "video_id": videodb_id,
        "title": video["title"],
        "source_url": video["source_url"],
        "duration_s": video["duration_s"],
        "pacing": pacing_summary,
        "technique_total": len(detections),
        "techniques": techniques,
        "headline": _headline(video["title"], pacing_summary, techniques),
    }


def _headline(title, pacing_summary, techniques):
    """One sentence an editor can read before anything else."""
    if not techniques:
        if pacing_summary:
            return (f"No transitions from the current vocabulary were detected. The edit runs "
                    f"{pacing_summary['cuts']} cuts at {pacing_summary['cuts_per_minute']} per "
                    f"minute (average shot {pacing_summary['avg_cut_length_s']}s).")
        return "Nothing detected yet."
    named = ", ".join(f"{t['count']}x {t['label'].lower()}" for t in techniques[:4])
    if pacing_summary:
        rhythm = " with rhythmic cutting" if pacing_summary["rhythm"]["rhythmic"] else ""
        return (f"{named} — cut at {pacing_summary['cuts_per_minute']} cuts/min, "
                f"average shot {pacing_summary['avg_cut_length_s']}s{rhythm}.")
    return named
