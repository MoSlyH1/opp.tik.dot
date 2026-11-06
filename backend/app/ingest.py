"""Fills the catalogue from curated nostalgic queries.

Run once:      python -m app.ingest
Run forever:   python -m app.worker        (Docker)
Run on cron:   GET /api/cron/ingest         (Vercel Cron)
"""

import logging
import random
from pathlib import Path

from flask import current_app

from .providers import archive, tiktok, youtube
from .store import upsert_items

log = logging.getLogger(__name__)

# (query, era hint, category hint)
YOUTUBE_SEEDS = [
    ("90s music video official", "90s", "music"),
    ("2000s music video official", "00s", "music"),
    ("80s music video classic", "classic", "music"),
    ("90s movie trailer", "90s", "movies"),
    ("2000s movie trailer original", "00s", "movies"),
    ("80s movie trailer", "classic", "movies"),
    ("90s fashion runway", "90s", "style"),
    ("y2k fashion 2000s style", "00s", "style"),
    ("90s commercials compilation", "90s", "ads"),
    ("2000s commercials compilation", "00s", "ads"),
    ("90s cartoon intro", "90s", "tv"),
    ("2000s tv show intro", "00s", "tv"),
    ("nokia commercial 2000s", "00s", "tech"),
    ("windows 98 commercial", "90s", "tech"),
    ("playstation 1 commercial 90s", "90s", "games"),
    ("ps2 commercial 2000s", "00s", "games"),
]

# (lucene query, category hint, mediatype)
ARCHIVE_SEEDS = [
    ("subject:(commercial OR commercials OR advertisement)", "ads", "movies"),
    ('subject:("music video" OR "music videos")', "music", "movies"),
    ("subject:(trailer OR trailers)", "movies", "movies"),
    ("subject:(cartoon OR cartoons OR animation)", "tv", "movies"),
    ("subject:(\"video game\" OR gameplay OR nintendo OR playstation)", "games", "movies"),
    ("subject:(fashion OR clothing OR style)", "style", "image"),
]
ERA_RANGES = {"classic": (1950, 1989), "90s": (1990, 1999), "00s": (2000, 2009)}

SEEDS_FILE = Path(__file__).resolve().parent.parent / "tiktok_seeds.txt"


def ingest_tiktok_urls(urls, force=True):
    raw = []
    for u in urls:
        try:
            d = tiktok.fetch(u)
            if d:
                raw.append(d)
        except Exception as e:  # network / bad URL
            log.warning("tiktok oembed failed for %s: %s", u, e)
    return upsert_items(raw, force=force)


def run(max_queries: int | None = None, per_query: int = 15) -> dict:
    stats = {"youtube": 0, "archive": 0, "tiktok": 0, "errors": 0}
    max_year = current_app.config["MAX_YEAR"]
    jobs = []
    if current_app.config["YOUTUBE_API_KEY"]:
        jobs += [("youtube", s) for s in YOUTUBE_SEEDS]
    for q, cat, media in ARCHIVE_SEEDS:
        for era, (y0, y1) in ERA_RANGES.items():
            jobs.append(("archive", (q, cat, media, era, y0, min(y1, max_year))))
    random.shuffle(jobs)
    if max_queries:
        jobs = jobs[:max_queries]

    for kind, spec in jobs:
        try:
            if kind == "youtube":
                q, era, cat = spec
                raw = youtube.search(current_app.config["YOUTUBE_API_KEY"], q, per_query)
                stats["youtube"] += len(upsert_items(raw, hint_era=era, hint_category=cat))
            else:
                q, cat, media, era, y0, y1 = spec
                raw = archive.search(q, rows=per_query, mediatype=media, year_from=y0, year_to=y1)
                stats["archive"] += len(upsert_items(raw, hint_era=era, hint_category=cat))
        except Exception as e:
            stats["errors"] += 1
            log.warning("ingest %s failed: %s", kind, e)

    if SEEDS_FILE.exists():
        urls = [l.strip() for l in SEEDS_FILE.read_text().splitlines()
                if l.strip() and not l.startswith("#")]
        stats["tiktok"] = len(ingest_tiktok_urls(urls))
    return stats


if __name__ == "__main__":
    from . import create_app

    logging.basicConfig(level=logging.INFO)
    with create_app().app_context():
        print(run())
