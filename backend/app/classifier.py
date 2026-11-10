"""Decides whether a piece of content is nostalgic, which era it belongs to, and
every topic / culture / channel it fits. Rule-based on purpose: fast, explainable,
free, and works in English, Arabic, French, Spanish, Portuguese, German and Turkish.
Swap for an embedding model later without touching the rest of the app."""

import re
from collections import Counter
from functools import lru_cache

from .taxonomy import (CHANNELS, COUNTRY_REGIONS, ERA_RANGES, FALLBACK_TOPIC, LANG_REGIONS,
                       REGION_PARENT, REGIONS, TOPICS)

YEAR_RE = re.compile(r"(?<!\d)(19[3-9]\d|20[0-2]\d)(?!\d)")

ERA_TERMS = [(re.compile(p, re.I), era) for p, era in [
    (r"\by2k\b|\bnoughties\b|\b(?:20)?00'?s\b|\b2000s\b", "00s"),
    (r"\b(?:19)?90'?s\b|\bnineties\b|\b90er\b|\b90'lar\b|años 90|anos 90|années 90|التسعينات|تسعينات", "90s"),
    (r"\b(?:19)?80'?s\b|\beighties\b|\b80er\b|\b80'ler\b|años 80|anos 80|années 80|الثمانينات|ثمانينات", "80s"),
    (r"\b(?:19)?70'?s\b|\bseventies\b|años 70|anos 70|années 70|السبعينات", "70s"),
    (r"\b(?:19)?60'?s\b|\bsixties\b|años 60|années 60|الستينات", "60s"),
    (r"\b(?:19)?[45]0'?s\b|\bfifties\b|\bforties\b|الخمسينات", "50s"),
]]

NOSTALGIA_TERMS = re.compile(
    r"\b(throwback|nostalgi\w*|retro|vintage|vhs|old school|childhood|millennial|tbt|remember when|"
    r"classic|classics|rewind|oldies|analog|camcorder|rare footage|original broadcast|archive footage|"
    r"recuerdos|nostalgia|souvenirs|kindheit|eski)\b|زمن الطيبين|الزمن الجميل|ذكريات|قديم|نادر|طفولتنا",
    re.I)
MODERN_TERMS = re.compile(
    r"\b(reaction|reacts|react to|ranking|tier list|ai generated|remake 20[12]\d|tiktok trend|"
    r"unboxing 20[12]\d|iphone 1[1-9]|ps5|fortnite)\b", re.I)


def year_to_era(year: int, max_year: int = 2009) -> str | None:
    if not year or year > max_year:
        return None
    for era, (y0, y1) in ERA_RANGES.items():
        if y0 <= year <= y1:
            return era
    return "50s" if year < 1930 else None


@lru_cache(maxsize=1)
def _compiled():
    def rx(words):
        parts = [w if "(?" in w else re.escape(w) for w in words]
        # \b doesn't work next to '+' or '.', so use look-arounds on "word" characters instead.
        return re.compile(r"(?<![\w])(?:" + "|".join(parts) + r")(?![\w])", re.I)
    topics = [(t[0], rx(t[3])) for t in TOPICS]
    regions = [(r[0], rx(r[4])) for r in REGIONS]
    channels = [(c[0], rx(c[2]), c[3], c[4]) for c in CHANNELS]
    return topics, regions, channels


SCRIPTS = [
    (re.compile(r"[پچژگ]"), "persian"),
    (re.compile(r"[؀-ۿ]"), "arabic"),
    (re.compile(r"[぀-ヿ]"), "japanese"),
    (re.compile(r"[가-힯]"), "korean"),
    (re.compile(r"[一-鿿]"), "chinese"),
    (re.compile(r"[Ѐ-ӿ]"), "russian"),
    (re.compile(r"[ऀ-ॿ஀-௿]"), "indian"),
    (re.compile(r"[฀-๿]"), "seasian"),
]


def _prep(text: str) -> str:
    # Disambiguate before matching.
    text = re.sub(r"american football|\bnfl\b", " gridiron american ", text)
    text = re.sub(r"harrison ford|gerald ford|tom ford", " ", text)
    return text


def classify(title="", description="", tags=None, year=None, hint_era=None, hint_category=None,
             max_year=2009, hint_topic=None, hint_region=None, lang=None, country=None) -> dict:
    hint_topic = hint_topic or hint_category
    tags = [str(t) for t in (tags or []) if t]
    raw = " ".join(filter(None, [title or "", description or "", " ".join(tags)]))
    text = _prep(raw.lower())
    title_l = _prep((title or "").lower())

    votes: Counter = Counter()
    score = 0.0

    # 1. Structured year (e.g. Internet Archive metadata) is the strongest signal.
    found_year = None
    if year and 1900 <= int(year) <= max_year:
        found_year = int(year)
        votes[year_to_era(found_year, max_year)] += 3
        score += 0.45

    # 2. Years written in the text.
    years = [int(y) for y in YEAR_RE.findall(text)]
    old_years = [y for y in years if y <= max_year]
    new_years = [y for y in years if y > max_year]
    for y in old_years:
        votes[year_to_era(y, max_year)] += 2 if str(y) in title_l else 1
    if old_years:
        score += 0.35
        found_year = found_year or Counter(old_years).most_common(1)[0][0]

    # 3. Era words, in several languages ("90s", "y2k", "années 80", "التسعينات"...).
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
    votes.pop(None, None)
    era = votes.most_common(1)[0][0] if votes else None

    # ---- labels
    topics_rx, regions_rx, channels_rx = _compiled()
    t_score: Counter = Counter()
    r_score: Counter = Counter()
    channels = []
    for tid, rx in topics_rx:
        n = len(rx.findall(text))
        if n:
            t_score[tid] += min(n, 3) + (1 if rx.search(title_l) else 0)
    for rid, rx in regions_rx:
        n = len(rx.findall(text))
        if n:
            r_score[rid] += min(n, 3) + (1 if rx.search(title_l) else 0)
    for cid, rx, imp_t, imp_r in channels_rx:
        if rx.search(text):
            channels.append(cid)
            for t in imp_t:
                t_score[t] += 0.8
            for r in imp_r:
                r_score[r] += 0.8
    if hint_topic:
        t_score[hint_topic] += 1.0
    if hint_region:
        r_score[hint_region] += 1.5
    if t_score.get("anime"):
        r_score["japanese"] += 1
    for rx, rid in SCRIPTS:
        if rx.search(raw):
            r_score[rid] += 2
            break
    for code in re.split(r"[;,/ ]+", (lang or "").lower()):
        for rid in LANG_REGIONS.get(code, []):
            r_score[rid] += 2
    if country and COUNTRY_REGIONS.get(country.upper()):
        r_score[COUNTRY_REGIONS[country.upper()]] += 1.5

    topics = [t for t, s in t_score.most_common() if s >= 1][:3]
    regions = [r for r, s in r_score.most_common() if s >= 1][:3]
    for r in list(regions):  # "Lebanese" is also "Arabic", "Japanese" is also "Asian"...
        p = REGION_PARENT.get(r)
        if p and p not in regions:
            regions.append(p)
    category = topics[0] if topics else FALLBACK_TOPIC[0]
    if topics:
        score += 0.1

    score = max(0.0, min(1.0, score))
    hashtags = re.findall(r"#(\w+)", text)
    return {
        "accepted": era is not None and score >= 0.3,
        "era": era,
        "year": found_year,
        "category": category,
        "topics": topics or [FALLBACK_TOPIC[0]],
        "regions": regions,
        "channels": channels[:3],
        "labels": labels_string(topics or [FALLBACK_TOPIC[0]], regions, channels[:3]),
        "score": round(score, 3),
        "tags": list(dict.fromkeys(hashtags + tags))[:12],
    }


def labels_string(topics, regions, channels) -> str:
    toks = [f"t:{t}" for t in topics] + [f"r:{r}" for r in regions] + [f"c:{c}" for c in channels]
    return ("|" + "|".join(toks) + "|") if toks else ""
