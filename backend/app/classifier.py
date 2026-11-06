"""Decides whether a piece of content is nostalgic, which era it belongs to,
and which category it fits. Rule-based on purpose: fast, explainable, free.
Swap for an embedding model later without touching the rest of the app."""

import re
from collections import Counter

YEAR_RE = re.compile(r"(?<!\d)(19[4-9]\d|20[0-2]\d)(?!\d)")

ERA_TERMS = [
    (r"\by2k\b", "00s"),
    (r"\b(?:20)?00'?s\b", "00s"),
    (r"\bnoughties\b", "00s"),
    (r"\b(?:19)?90'?s\b", "90s"),
    (r"\bnineties\b", "90s"),
    (r"\b(?:19)?[5-8]0'?s\b", "classic"),
    (r"\b(?:fifties|sixties|seventies|eighties)\b", "classic"),
]
ERA_TERMS = [(re.compile(p), era) for p, era in ERA_TERMS]

NOSTALGIA_TERMS = re.compile(
    r"\b(throwback|nostalgi\w*|retro|vintage|vhs|old school|childhood|millennial|tbt|"
    r"remember when|classic|rewind|oldies|analog|camcorder)\b"
)
MODERN_TERMS = re.compile(r"\b(reaction|reacts|react to|ranking|tier list|ai generated|remake 20[12]\d)\b")

CATEGORY_KEYWORDS = {
    "music": ["music video", "official video", "official music", "song", "album", "mtv",
              "band", "live performance", "concert", "single", "hip hop", "pop", "rnb", "boy band"],
    "movies": ["movie", "film", "trailer", "scene", "cinema", "box office", "blockbuster"],
    "style": ["fashion", "style", "outfit", "runway", "hairstyle", "makeup", "clothing",
              "trend", "lookbook", "streetwear", "denim", "y2k aesthetic"],
    "tv": ["tv", "sitcom", "cartoon", "series", "episode", "nickelodeon", "cartoon network",
           "theme song", "intro", "opening", "anime", "saturday morning"],
    "ads": ["commercial", "commercials", "ad", "ads", "advert", "advertisement", "promo", "jingle"],
    "tech": ["nokia", "walkman", "discman", "ipod", "windows 95", "windows 98", "windows xp",
             "dial-up", "dial up", "flip phone", "tamagotchi", "msn", "aol", "computer", "pager", "blackberry"],
    "games": ["game", "games", "playstation", "ps1", "ps2", "nintendo", "n64", "sega", "gameboy",
              "game boy", "arcade", "gameplay", "xbox", "gamecube"],
}
_CATEGORY_RES = {
    cat: [re.compile(r"\b" + re.escape(k) + r"\b") for k in kws] for cat, kws in CATEGORY_KEYWORDS.items()
}


def year_to_era(year: int) -> str | None:
    if year < 1990:
        return "classic"
    if year < 2000:
        return "90s"
    if year <= 2009:
        return "00s"
    return None


def classify(title="", description="", tags=None, year=None, hint_era=None,
             hint_category=None, max_year=2009) -> dict:
    text = " ".join(filter(None, [title or "", description or "", " ".join(tags or [])])).lower()
    title_l = (title or "").lower()

    votes: Counter = Counter()
    score = 0.0

    # 1. Structured year (e.g. Internet Archive metadata) is the strongest signal.
    found_year = None
    if year and 1940 <= int(year) <= max_year:
        found_year = int(year)
        votes[year_to_era(found_year)] += 3
        score += 0.45

    # 2. Years written in the text.
    years = [int(y) for y in YEAR_RE.findall(text)]
    old_years = [y for y in years if y <= max_year]
    new_years = [y for y in years if y > max_year]
    for y in old_years:
        votes[year_to_era(y)] += 2 if str(y) in title_l else 1
    if old_years:
        score += 0.35
        found_year = found_year or Counter(old_years).most_common(1)[0][0]

    # 3. Era words ("90s", "y2k", "eighties"...).
    era_hits = 0
    for rx, era in ERA_TERMS:
        if rx.search(text):
            votes[era] += 1.5
            era_hits += 1
    if era_hits:
        score += 0.3

    # 4. General nostalgia vocabulary.
    score += min(0.3, 0.1 * len(NOSTALGIA_TERMS.findall(text)))

    # 5. The query that found it (curated seed / user's era filter).
    if hint_era:
        votes[hint_era] += 0.75
        score += 0.3

    # Penalties: clearly modern content.
    if new_years and not old_years and not found_year:
        score -= 0.5
    if MODERN_TERMS.search(text):
        score -= 0.3

    era = votes.most_common(1)[0][0] if votes else None

    cat_scores = Counter()
    for cat, regs in _CATEGORY_RES.items():
        hits = sum(1 for r in regs if r.search(text))
        if hits:
            cat_scores[cat] = hits
    if hint_category:
        cat_scores[hint_category] += 0.5
    category = cat_scores.most_common(1)[0][0] if cat_scores else "culture"
    if cat_scores:
        score += 0.1

    score = max(0.0, min(1.0, score))
    hashtags = re.findall(r"#(\w+)", text)
    return {
        "accepted": era is not None and score >= 0.3,
        "era": era,
        "year": found_year,
        "category": category,
        "score": round(score, 3),
        "tags": list(dict.fromkeys(hashtags + list(tags or [])))[:12],
    }
