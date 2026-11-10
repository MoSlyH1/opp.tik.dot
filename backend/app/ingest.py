"""Fills the catalogue from curated nostalgic queries, across every topic and culture.

Run once:      python -m app.ingest
Run forever:   python -m app.worker        (Docker)
Run on cron:   GET /api/cron/ingest         (Vercel Cron)

Each run picks a sample of seeds, favouring the topics/cultures the catalogue has
the fewest items for, so filters like "Lebanese" or "Documentaries" fill up instead
of the catalogue drifting towards whatever is most popular.
"""

import logging
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from flask import current_app

from .extensions import db
from .models import Item
from .providers import archive, dailymotion, social, tiktok, youtube
from .store import reclassify, resolve_backlog, upsert_items
from .taxonomy import ERA_RANGES

log = logging.getLogger(__name__)


@dataclass
class Seed:
    source: str
    query: str
    era: str | None = None
    topic: str | None = None
    region: str | None = None
    opts: dict = field(default_factory=dict)

    @property
    def facets(self):
        return [f for f in (self.topic and f"t:{self.topic}", self.region and f"r:{self.region}") if f]


def _yt(q, era=None, topic=None, region=None, **o):
    return Seed("youtube", q, era, topic, region, o)


def _dm(q, era=None, topic=None, region=None, **o):
    return Seed("dailymotion", q, era, topic, region, o)


YOUTUBE_SEEDS = [
    # music, by era and by culture
    _yt("80s music video official", "80s", "music"), _yt("90s music video official", "90s", "music"),
    _yt("2000s music video official", "00s", "music"), _yt("70s music live performance", "70s", "music"),
    _yt("60s music live tv performance", "60s", "music"),
    _yt("eurodance 90s official video", "90s", "music", "european"),
    _yt("britpop 90s official video", "90s", "music", "british"),
    _yt("اغاني لبنانية قديمة", None, "music", "lebanese", lang="ar"),
    _yt("اغاني التسعينات العربية فيديو كليب", "90s", "music", "arabic", lang="ar"),
    _yt("اغاني مصرية قديمة الثمانينات", "80s", "music", "egyptian", lang="ar"),
    _yt("اغاني خليجية قديمة زمن الطيبين", None, "music", "gulf", lang="ar"),
    _yt("cheb khaled 90s clip", "90s", "music", "maghreb"),
    _yt("latin pop 90s video oficial", "90s", "music", "latin", lang="es"),
    _yt("musica brasileira anos 80 clipe", "80s", "music", "brazilian", lang="pt"),
    _yt("chanson française années 80 clip", "80s", "music", "french", lang="fr"),
    _yt("italo disco 80s video", "80s", "music", "italian"),
    _yt("bollywood 90s songs video", "90s", "music", "indian", lang="hi"),
    _yt("90s j-pop music video", "90s", "music", "japanese", lang="ja"),
    _yt("1990s k-pop music video", "90s", "music", "korean", lang="ko"),
    _yt("cantopop 80s music video", "80s", "music", "chinese"),
    _yt("tarkan 90s klip", "90s", "music", "turkish", lang="tr"),
    _yt("soviet 80s music video", "80s", "music", "russian", lang="ru"),
    _yt("afrobeat 1970s live", "70s", "music", "african"),
    # kids & cartoons & anime
    _yt("90s cartoon intro", "90s", "kids", "american"), _yt("2000s cartoon network shows intro", "00s", "kids"),
    _yt("80s saturday morning cartoons intro", "80s", "kids", "american"),
    _yt("nickelodeon 90s commercials", "90s", "kids"), _yt("fox kids 1990s bumpers", "90s", "kids"),
    _yt("شارات كرتون سبيستون القديمة", "90s", "kids", "arabic", lang="ar"),
    _yt("كرتون زمان الثمانينات", "80s", "kids", "arabic", lang="ar"),
    _yt("génériques dessins animés années 80", "80s", "kids", "french", lang="fr"),
    _yt("dibujos animados años 90 intro", "90s", "kids", "latin", lang="es"),
    _yt("90s anime opening", "90s", "anime", "japanese"), _yt("80s anime opening", "80s", "anime", "japanese"),
    # documentaries, sci-fi, horror, comedy, drama
    _yt("national geographic documentary 1990s", "90s", "docs"),
    _yt("discovery channel documentary 1990s", "90s", "docs"),
    _yt("BBC documentary 1980s", "80s", "docs", "british"),
    _yt("وثائقي قديم الثمانينات", "80s", "docs", "arabic", lang="ar"),
    _yt("90s sci-fi movie trailer", "90s", "scifi"), _yt("80s sci-fi movie trailer", "80s", "scifi"),
    _yt("70s science fiction trailer", "70s", "scifi"),
    _yt("80s horror movie trailer", "80s", "horror"), _yt("90s horror trailer", "90s", "horror"),
    _yt("90s sitcom intro", "90s", "comedy", "american"), _yt("2000s sitcom bloopers", "00s", "comedy"),
    _yt("مسرحيات كوميدية قديمة", None, "comedy", "arabic", lang="ar"),
    _yt("telenovela años 90 entrada", "90s", "drama", "latin", lang="es"),
    _yt("مسلسلات لبنانية قديمة شارة", None, "drama", "lebanese", lang="ar"),
    _yt("مسلسلات مصرية قديمة تتر", None, "drama", "egyptian", lang="ar"),
    # movies
    _yt("90s movie trailer", "90s", "movies"), _yt("2000s movie trailer original", "00s", "movies"),
    _yt("80s movie trailer", "80s", "movies"), _yt("70s movie trailer", "70s", "movies"),
    _yt("افلام مصرية قديمة مشهد", None, "movies", "egyptian", lang="ar"),
    _yt("hong kong action movie trailer 80s", "80s", "movies", "chinese"),
    _yt("bollywood 90s movie trailer", "90s", "movies", "indian"),
    _yt("yeşilçam film fragman", "70s", "movies", "turkish", lang="tr"),
    # sports
    _yt("world cup 1998 goals", "90s", "football"), _yt("world cup 1990 highlights", "90s", "football"),
    _yt("world cup 1986 maradona", "80s", "football"), _yt("euro 2000 best goals", "00s", "football"),
    _yt("champions league 1999 final highlights", "90s", "football"),
    _yt("كأس العالم 1998 اهداف بتعليق عربي", "90s", "football", "arabic", lang="ar"),
    _yt("مباريات قديمة الدوري المصري", None, "football", "egyptian", lang="ar"),
    _yt("goles del mundial 1994", "90s", "football", "latin", lang="es"),
    _yt("formula 1 1990s highlights", "90s", "motorsport"), _yt("senna 1988 onboard", "80s", "motorsport"),
    _yt("nba 90s highlights", "90s", "basketball", "american"),
    _yt("wwf 1990s entrance", "90s", "combat", "american"), _yt("mike tyson 1980s knockouts", "80s", "combat"),
    _yt("olympics 1996 atlanta highlights", "90s", "sports"),
    # cars
    _yt("80s car commercial", "80s", "cars"), _yt("90s car commercial", "90s", "cars"),
    _yt("top gear 2003 review", "00s", "cars", "british"), _yt("jdm 90s car commercial japan", "90s", "cars", "japanese"),
    _yt("motor show 1990s supercars", "90s", "cars"),
    # commercials, by culture
    _yt("90s commercials compilation", "90s", "ads", "american"), _yt("80s commercials compilation", "80s", "ads", "american"),
    _yt("2000s commercials compilation", "00s", "ads"),
    _yt("pubs années 90", "90s", "ads", "french", lang="fr", rc="FR"),
    _yt("werbung 90er", "90s", "ads", "german", lang="de"),
    _yt("spot pubblicitari anni 80", "80s", "ads", "italian", lang="it"),
    _yt("anuncios años 90 españa", "90s", "ads", "spanish", lang="es", rc="ES"),
    _yt("comerciales mexicanos años 90", "90s", "ads", "mexican", lang="es", rc="MX"),
    _yt("propagandas antigas anos 90", "90s", "ads", "brazilian", lang="pt", rc="BR"),
    _yt("اعلانات زمان التسعينات", "90s", "ads", "arabic", lang="ar"),
    _yt("اعلانات لبنانية قديمة", None, "ads", "lebanese", lang="ar"),
    _yt("اعلانات مصرية قديمة", None, "ads", "egyptian", lang="ar"),
    _yt("90s japanese commercials", "90s", "ads", "japanese"),
    _yt("doordarshan ads 90s", "90s", "ads", "indian"),
    _yt("eski reklamlar 90'lar", "90s", "ads", "turkish", lang="tr"),
    _yt("soviet commercials 80s", "80s", "ads", "russian"),
    # TV world
    _yt("1990s news broadcast", "90s", "news"), _yt("نشرة اخبار قديمة تلفزيون لبنان", None, "news", "lebanese", lang="ar"),
    _yt("1990s tv idents", "90s", "idents"), _yt("mtv idents 90s", "90s", "idents"),
    _yt("lbc 90s ident", "90s", "idents", "lebanese"), _yt("spacetoon bumpers", "00s", "idents", "arabic"),
    # tech, games, style, dance, food, travel
    _yt("windows 95 commercial", "90s", "tech"), _yt("nokia commercial 2000s", "00s", "tech"),
    _yt("msn messenger 2005 nostalgia", "00s", "tech"),
    _yt("playstation 1 commercial 90s", "90s", "games"), _yt("ps2 commercial 2000s", "00s", "games"),
    _yt("sega genesis commercial", "90s", "games"), _yt("nintendo 64 commercials", "90s", "games"),
    _yt("90s fashion runway", "90s", "style"), _yt("y2k fashion 2000s style", "00s", "style"),
    _yt("80s aerobics dance", "80s", "dance"), _yt("dabke 1980s wedding", "80s", "dance", "lebanese"),
    _yt("90s cooking show", "90s", "food"), _yt("1980s home video street", "80s", "travel"),
    _yt("beirut 1970s footage", "70s", "travel", "lebanese"), _yt("cairo 1960s footage", "60s", "travel", "egyptian"),
]

DAILYMOTION_SEEDS = [
    _dm("pub années 80", "80s", "ads", "french", lang="fr"), _dm("pub années 90", "90s", "ads", "french", lang="fr"),
    _dm("générique dessin animé années 80", "80s", "kids", "french", lang="fr"),
    _dm("spacetoon", "90s", "kids", "arabic", lang="ar"), _dm("كرتون قديم", None, "kids", "arabic", lang="ar"),
    _dm("مسلسل لبناني قديم", None, "drama", "lebanese", lang="ar"),
    _dm("اعلانات قديمة", None, "ads", "arabic", lang="ar"), _dm("فيلم مصري قديم", None, "movies", "egyptian", lang="ar"),
    _dm("pubblicità anni 80", "80s", "ads", "italian", lang="it"), _dm("sigle cartoni animati anni 80", "80s", "kids", "italian", lang="it"),
    _dm("werbung 80er", "80s", "ads", "german", lang="de"), _dm("comerciales años 80", "80s", "ads", "latin", lang="es"),
    _dm("anime opening 90s", "90s", "anime", "japanese"), _dm("coupe du monde 1998 buts", "90s", "football", "french", lang="fr"),
    _dm("formule 1 1990", "90s", "motorsport"), _dm("rallye années 80", "80s", "motorsport"),
    _dm("documentaire années 70", "70s", "docs", "french", lang="fr"), _dm("clip années 80", "80s", "music", "french", lang="fr"),
    _dm("90s music video", "90s", "music"), _dm("80s cartoon intro", "80s", "kids"),
    _dm("jingle tv 80s", "80s", "idents"), _dm("vieille voiture publicité", "80s", "cars", "french", lang="fr"),
    _dm("série culte années 80 générique", "80s", "tv", "french", lang="fr"),
]

# (lucene subject/collection query, topic hint)
ARCHIVE_SUBJECTS = [
    ("subject:(commercial OR commercials OR advertisement)", "ads"),
    ('subject:("music video" OR "music videos")', "music"),
    ("subject:(trailer OR trailers)", "movies"),
    ("subject:(cartoon OR cartoons OR animation)", "kids"),
    ('subject:("video game" OR gameplay OR nintendo OR playstation)', "games"),
    ("subject:(documentary OR documentaries)", "docs"),
    ('subject:("science fiction" OR sci-fi OR scifi)', "scifi"),
    ("subject:(horror)", "horror"),
    ('subject:(football OR soccer OR "world cup")', "football"),
    ('subject:(automobile OR automobiles OR cars OR "car commercial")', "cars"),
    ('subject:("news broadcast" OR newscast OR "tv news")', "news"),
    ('subject:(ident OR idents OR bumper OR bumpers OR "station id")', "idents"),
    ('subject:(sitcom OR "tv show" OR "television series")', "tv"),
    ("subject:(sports OR olympics OR boxing OR wrestling)", "sports"),
    ("subject:(anime)", "anime"),
    ("subject:(travelogue OR travel)", "travel"),
    ("subject:(fashion OR clothing)", "style"),
    ("collection:(prelinger)", "docs"),
    ("collection:(classic_tv_commercials)", "ads"),
    ("collection:(classic_cartoons)", "kids"),
    ("collection:(SciFi_Horror)", "scifi"),
    ("collection:(vhsvault)", None),
]
ARCHIVE_LANGS = [
    ("language:(arabic OR ara)", "arabic"), ("language:(french OR fre OR fra)", "french"),
    ("language:(spanish OR spa)", "latin"), ("language:(german OR ger OR deu)", "german"),
    ("language:(italian OR ita)", "italian"), ("language:(japanese OR jpn)", "japanese"),
    ("language:(russian OR rus)", "russian"), ("language:(portuguese OR por)", "brazilian"),
    ("language:(turkish OR tur)", "turkish"), ("language:(hindi OR hin)", "indian"),
    ("language:(chinese OR chi OR zho)", "chinese"), ("language:(korean OR kor)", "korean"),
]
ARCHIVE_LANG_TOPICS = ["subject:(commercial OR commercials OR advertisement)", "subject:(cartoon OR cartoons OR animation)",
                       "subject:(music OR song)", "subject:(film OR movie OR trailer)", "subject:(television OR tv)"]

REDDIT_SUBS = [("90s", "90s", None), ("2000s", "00s", None), ("80s", "80s", None), ("nostalgia", None, None),
               ("retrogaming", None, "games"), ("Cartoons", None, "kids"), ("90sHipHop", "90s", "music"),
               ("ObscureMedia", None, None), ("Lebanon", None, None)]
IG_HASHTAGS = ["90s", "90snostalgia", "2000snostalgia", "y2k", "90skids", "retro", "vhs", "oldcommercials",
               "retrofootball", "90sfootball", "classiccars", "jdm90s", "زمن_الطيبين", "lebanonvintage"]
X_QUERIES = ["#90s OR #90skids", "#y2k OR #2000s nostalgia", "#retrofootball", "#throwback 1990s",
             "#زمن_الطيبين", "#nostalgia vhs"]

SEEDS_FILE = Path(__file__).resolve().parent.parent / "tiktok_seeds.txt"


def archive_seeds(max_year: int) -> list[Seed]:
    out = []
    for q, topic in ARCHIVE_SUBJECTS:
        for era, (y0, y1) in ERA_RANGES.items():
            if y0 <= max_year:
                out.append(Seed("archive", q, era, topic, None, {"y0": y0, "y1": min(y1, max_year)}))
    for lq, region in ARCHIVE_LANGS:
        for tq in ARCHIVE_LANG_TOPICS:
            out.append(Seed("archive", f"{lq} AND {tq}", None, None, region, {"y0": 1930, "y1": max_year}))
    return out


def ingest_urls(urls, force=True, hint_era=None, hint_topic=None, hint_region=None):
    """Curated links from any supported platform (Curator panel / tiktok_seeds.txt)."""
    from .providers.links import from_url

    raw = []
    for u in urls:
        try:
            d = from_url(u, current_app.config)
            if d:
                raw.append(d)
        except Exception as e:  # network / bad URL
            log.warning("link import failed for %s: %s", u, e)
    if raw:
        try:
            raw = [r for r in raw if r["source"] != "youtube"] + youtube.enrich(
                current_app.config["YOUTUBE_API_KEY"], [r for r in raw if r["source"] == "youtube"])
        except Exception as e:
            log.warning("youtube enrich failed: %s", e)
    return upsert_items(raw, force=force, hint_era=hint_era, hint_topic=hint_topic, hint_region=hint_region)


ingest_tiktok_urls = ingest_urls  # v3 name


def _coverage() -> Counter:
    c = Counter()
    for (labels,) in db.session.query(Item.labels).filter(Item.hidden.is_(False)):
        c.update(t for t in (labels or "").strip("|").split("|") if t)
    return c


def _weighted_sample(seeds: list[Seed], k: int, cov: Counter) -> list[Seed]:
    """Sample without replacement, favouring under-filled topics/cultures."""
    pool = list(seeds)
    out = []
    while pool and len(out) < k:
        weights = [1.0 / (1 + min((cov[f] for f in s.facets), default=40) / 40) for s in pool]
        s = random.choices(pool, weights)[0]
        pool.remove(s)
        out.append(s)
    return out


def _fetch(seed: Seed, cfg: dict, per_query: int) -> list[dict]:
    o = seed.opts
    if seed.source == "youtube":
        return youtube.search(cfg["YOUTUBE_API_KEY"], seed.query, per_query, lang=o.get("lang"),
                              region=o.get("rc"), duration=o.get("duration"))
    if seed.source == "dailymotion":
        return dailymotion.search(seed.query, per_query, lang=o.get("lang"), kids=seed.topic == "kids")
    if seed.source == "archive":
        return archive.search(seed.query, rows=per_query, year_from=o["y0"], year_to=o["y1"],
                              sort=random.choice(["downloads desc", "week desc", "avg_rating desc"]))
    if seed.source == "reddit":
        return social.reddit_links(seed.query, cfg["REDDIT_CLIENT_ID"], cfg["REDDIT_CLIENT_SECRET"])
    if seed.source == "instagram":
        return social.instagram_hashtag(seed.query, cfg["META_ACCESS_TOKEN"], cfg["IG_USER_ID"])
    if seed.source == "x":
        return social.x_search(seed.query, cfg["X_BEARER_TOKEN"])
    return []


def run(max_queries: int | None = None, per_query: int = 15, budget_s: float = 45) -> dict:
    cfg = current_app.config
    t0 = time.time()
    stats = Counter()
    stats["relabelled"] = reclassify(limit=3000)

    full = max_queries is None
    n = max_queries or 10**6
    cov = _coverage()
    jobs: list[Seed] = []
    if cfg["YOUTUBE_API_KEY"]:
        # ~101 quota units per seed; keep a run well inside the 10k/day default.
        jobs += _weighted_sample(YOUTUBE_SEEDS, 24 if full else max(2, n // 3), cov)
    jobs += _weighted_sample(archive_seeds(cfg["MAX_YEAR"]), 10**6 if full else max(2, n // 3), cov)
    if cfg["DAILYMOTION"]:
        jobs += _weighted_sample(DAILYMOTION_SEEDS, 10**6 if full else max(1, n // 4), cov)
    if cfg["REDDIT_CLIENT_ID"]:
        jobs += [Seed("reddit", s, e, t) for s, e, t in random.sample(REDDIT_SUBS, 3)]
    if cfg["META_ACCESS_TOKEN"] and cfg["IG_USER_ID"]:
        jobs += [Seed("instagram", h) for h in random.sample(IG_HASHTAGS, 2)]  # 30 tags / 7 days limit
    if cfg["X_BEARER_TOKEN"]:
        jobs += [Seed("x", random.choice(X_QUERIES))]
    random.shuffle(jobs)
    if not full:
        jobs = jobs[:max(n, 4)]

    # Network in parallel, database writes on this thread.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_fetch, s, cfg, per_query): s for s in jobs}
        for fut in as_completed(futs):
            seed = futs[fut]
            try:
                raw = fut.result()
                added = upsert_items(raw, hint_era=seed.era, hint_topic=seed.topic, hint_region=seed.region,
                                     resolve=time.time() - t0 < budget_s)
                stats[seed.source] += len(added)
            except Exception as e:
                stats["errors"] += 1
                log.warning("ingest %s %r failed: %s", seed.source, seed.query, e)
            if time.time() - t0 > budget_s and not full:
                for f in futs:
                    f.cancel()
                break

    if time.time() - t0 < budget_s and SEEDS_FILE.exists():
        urls = [l.strip() for l in SEEDS_FILE.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")]
        stats["curated"] = len(ingest_urls(urls))
    if time.time() - t0 < budget_s + 5:
        stats["archive_resolved"] = resolve_backlog(40, upgrade=120)
    stats["seconds"] = round(time.time() - t0, 1)
    return dict(stats)


if __name__ == "__main__":
    from . import create_app

    logging.basicConfig(level=logging.INFO)
    with create_app().app_context():
        print(run())
