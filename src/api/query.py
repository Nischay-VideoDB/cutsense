"""Plain-language query → a structured retrieval plan.

"find match cuts in sneaker ads" has to become a technique filter AND a content
filter; "which videos cut on the beat?" is not a clip search at all, it is a
pacing question. So the parser returns an intent alongside the filters, and the
API routes on it.

An LLM does the parsing (via VideoDB's own text generation, so the app needs no
second provider), with a keyword fallback that keeps search working when the model
is unavailable — a dead search box is worse than a blunt one.
"""

import json
import re

from src.detect.prompts import SHIPPING_TECHNIQUES, TECHNIQUE_LABELS

INTENTS = ("clips", "pacing", "profile", "reel")

PARSE_PROMPT = """Turn an editor's question about a video reference library into a retrieval plan.

Available techniques (use these exact ids): {techniques}

Intents:
- "clips": they want playable moments of a technique (default)
- "pacing": they are asking about cutting speed or rhythm ("which videos cut on the beat",
  "fastest cut ads", "what has the quickest pacing")
- "profile": they are asking about a creator's or brand's editing style
- "reel": they explicitly ask for a compilation, study reel, supercut or montage

Question: "{query}"

Return ONLY JSON:
{{"intent": "<one intent>",
  "techniques": [<technique ids, empty if none named>],
  "content_terms": [<subject/brand/genre words to match against video titles and clip
                     descriptions, e.g. "sneaker", "ad", "music video"; empty if none>],
  "creator": "<creator or brand name if one is named, else empty>",
  "wants_fastest": <true if they want the fastest/most rhythmic cutting>}}"""

# fallback matching: technique id -> words that imply it
TECHNIQUE_WORDS = {
    "whip_pan": ["whip", "whip pan", "whip-pan", "swish", "pan transition"],
    "zoom_punch": ["zoom", "zoom punch", "crash zoom", "punch in", "punch-in"],
    "match_cut": ["match cut", "match-cut", "matchcut"],
    "graphic_match": ["graphic match", "graphic-match", "shape match"],
    "speed_ramp": ["speed ramp", "speed-ramp", "ramp", "slow mo", "slow-mo", "speed change"],
    "luma_fade": ["luma", "luma fade", "dip to black", "fade to black", "fade to white", "dip"],
}
PACING_WORDS = ["beat", "pacing", "cut frequency", "cuts per", "fast cut", "fastest",
                "rhythm", "rhythmic", "tempo", "quick cut"]
REEL_WORDS = ["reel", "compilation", "supercut", "montage", "stitch", "study reel"]
PROFILE_WORDS = ["style", "signature", "profile", "how does", "how do they"]


def fallback_plan(query):
    q = (query or "").lower()
    techniques = [t for t, words in TECHNIQUE_WORDS.items() if any(w in q for w in words)]
    intent = "clips"
    if any(w in q for w in REEL_WORDS):
        intent = "reel"
    elif any(w in q for w in PACING_WORDS):
        intent = "pacing"
    elif any(w in q for w in PROFILE_WORDS):
        intent = "profile"

    # content terms = leftover meaningful words
    stop = set("show me every all find the a an of in on with that which video videos clip clips"
               " editing edit cut cuts technique techniques give please".split())
    for words in TECHNIQUE_WORDS.values():
        stop.update(w for phrase in words for w in phrase.split())
    stop.update(PACING_WORDS + REEL_WORDS + PROFILE_WORDS)
    terms = [w for w in re.findall(r"[a-z']{3,}", q) if w not in stop]
    return {"intent": intent, "techniques": techniques, "content_terms": terms[:4],
            "creator": "", "wants_fastest": "fastest" in q or "quickest" in q,
            "parsed_by": "keywords"}


def parse(query, coll=None):
    """Return a retrieval plan for a plain-language question."""
    if not query or not query.strip():
        return {"intent": "clips", "techniques": [], "content_terms": [], "creator": "",
                "wants_fastest": False, "parsed_by": "empty"}
    if coll is None:
        return fallback_plan(query)
    try:
        raw = coll.generate_text(
            prompt=PARSE_PROMPT.format(techniques=", ".join(SHIPPING_TECHNIQUES), query=query),
            model_name="basic", response_type="json")
        payload = raw.get("output", raw) if isinstance(raw, dict) else json.loads(str(raw))
        intent = payload.get("intent") if payload.get("intent") in INTENTS else "clips"
        # the model reaches for "reel" whenever a query sounds collective ("every whip
        # pan"), so a reel must be asked for in the words, not inferred
        if intent == "reel" and not any(w in query.lower() for w in REEL_WORDS):
            intent = "clips"
        plan = {
            "intent": intent,
            "techniques": [t for t in (payload.get("techniques") or [])
                           if t in SHIPPING_TECHNIQUES],
            "content_terms": [str(t).lower() for t in (payload.get("content_terms") or [])][:5],
            "creator": (payload.get("creator") or "").strip(),
            "wants_fastest": bool(payload.get("wants_fastest")),
            "parsed_by": "llm",
        }
        # a plan with nothing in it is no better than the keyword pass
        if not (plan["techniques"] or plan["content_terms"] or plan["creator"]):
            fb = fallback_plan(query)
            fb["intent"] = plan["intent"]
            fb["parsed_by"] = "llm+keywords"
            return fb
        return plan
    except Exception:
        return fallback_plan(query)


def describe(plan):
    """Human-readable interpretation, shown back to the user so the query isn't a black box."""
    bits = []
    if plan["techniques"]:
        bits.append(" or ".join(TECHNIQUE_LABELS.get(t, t) for t in plan["techniques"]))
    else:
        bits.append("any technique")
    if plan["content_terms"]:
        bits.append("in " + ", ".join(plan["content_terms"]))
    if plan["creator"]:
        bits.append(f"by {plan['creator']}")
    if plan["intent"] == "pacing":
        return "Pacing question — ranking videos by cutting speed and rhythm"
    if plan["intent"] == "profile":
        return f"Style profile — {plan['creator'] or 'creator'}"
    if plan["intent"] == "reel":
        return "Study reel — " + " ".join(bits)
    return " ".join(bits)
