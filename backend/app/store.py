import logging
from concurrent.futures import ThreadPoolExecutor

from flask import current_app
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from .classifier import classify
from .extensions import db
from .models import Item
from .providers import archive
from .taxonomy import TAXONOMY_VERSION

log = logging.getLogger(__name__)


def _classify(r: dict, hint_era=None, hint_topic=None, hint_region=None) -> dict:
    return classify(r.get("title"), r.get("description"), r.get("tags"), r.get("year"),
                    hint_era=hint_era, hint_topic=hint_topic, hint_region=hint_region,
                    lang=r.get("lang"), country=r.get("country"),
                    max_year=current_app.config["MAX_YEAR"])


def upsert_items(raw_items, hint_era=None, hint_category=None, force=False, hint_region=None,
                 hint_topic=None, resolve=True) -> list[Item]:
    """Classify raw provider dicts and store the nostalgic ones.
    Existing items are returned untouched. `force` keeps items the classifier
    rejects (used when an admin hand-picks a link)."""
    hint_topic = hint_topic or hint_category
    out: list[Item] = []
    fresh: list[Item] = []
    for r in raw_items:
        if not r.get("external_id"):
            continue
        existing = Item.query.filter_by(source=r["source"], external_id=r["external_id"]).first()
        if existing:
            out.append(existing)
            continue
        c = _classify(r, hint_era, hint_topic, hint_region)
        if not c["accepted"] and not force:
            continue
        item = Item(
            source=r["source"], external_id=r["external_id"], kind=r.get("kind", "video"),
            url=r["url"], title=r.get("title") or "", author=r.get("author"),
            description=r.get("description"), thumbnail=r.get("thumbnail"),
            era=c["era"] or hint_era or "90s", year=c["year"],
            category=c["category"], labels=c["labels"], tax_v=TAXONOMY_VERSION,
            tags=c["tags"], score=max(c["score"], 0.5 if force else 0),
            lang=(r.get("lang") or None) and str(r["lang"])[:16], duration=r.get("duration"),
            media_url=r.get("media_url"),
        )
        try:
            with db.session.begin_nested():
                db.session.add(item)
            out.append(item)
            fresh.append(item)
        except IntegrityError:  # inserted concurrently by another worker
            dup = Item.query.filter_by(source=r["source"], external_id=r["external_id"]).first()
            if dup:
                out.append(dup)
    db.session.commit()
    if resolve:
        resolve_media([i for i in fresh if i.source == "archive"])
    return out


def _needs_upgrade(i: Item) -> bool:
    """Resolved before v6: knows one MP4 but not its renditions / storage server."""
    return i.source == "archive" and bool(i.media_url) and i.media_info is None


def resolve_media(items: list[Item], workers: int = 8, timeout: int = 6, upgrade: bool = False) -> None:
    """Find the playable MP4s for Internet Archive items (in parallel, network only in threads).
    `upgrade` also refreshes items resolved by older versions (adds renditions + direct server)."""
    todo = [i for i in items if i.source == "archive" and (i.media_url is None or (upgrade and _needs_upgrade(i)))]
    if not todo:
        return

    def work(pair):
        ident, kind = pair
        try:
            return archive.resolve(ident, kind, timeout=timeout)
        except Exception as e:  # network hiccup: leave NULL and try again later
            log.info("archive resolve failed for %s: %s", ident, e)
            return None

    with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as pool:
        results = list(pool.map(work, [(i.external_id, i.kind) for i in todo]))
    for item, res in zip(todo, results):
        if res is None:
            continue
        if not res["media_url"] and item.media_url:
            item.media_info = {}  # upgrade found nothing better: keep the old file, don't retry
            continue
        item.media_url = res["media_url"]
        item.media_info = res.get("media_info") or {}
        if res.get("duration"):
            item.duration = res["duration"]
    db.session.commit()


def resolve_backlog(limit: int = 60, upgrade: int = 0, timeout: int = 6) -> int:
    """Resolve never-resolved Archive items, then (optionally) upgrade up to `upgrade` older ones."""
    items = (Item.query.filter(Item.source == "archive", Item.media_url.is_(None), Item.hidden.is_(False))
             .order_by(Item.score.desc()).limit(limit).all())
    if upgrade:
        items += (Item.query.filter(Item.source == "archive", Item.media_url.isnot(None), Item.media_url != "",
                                    Item.media_info.is_(None), Item.hidden.is_(False))
                  .order_by(Item.impressions.desc(), Item.score.desc()).limit(upgrade).all())
    for i in range(0, len(items), 40):
        resolve_media(items[i:i + 40], timeout=timeout, upgrade=True)
    return len(items)


def reclassify(limit: int = 2000) -> int:
    """Re-label items stored by an older taxonomy (new topics/cultures/channels, split eras)."""
    items = (Item.query.filter(or_(Item.tax_v < TAXONOMY_VERSION, Item.tax_v.is_(None)))
             .order_by(Item.id).limit(limit).all())
    for it in items:
        c = classify(it.title, it.description, it.tags, it.year, lang=it.lang,
                     hint_topic=it.category if it.category != "culture" else None,
                     max_year=current_app.config["MAX_YEAR"])
        it.labels = c["labels"]
        it.category = c["category"]
        if c["era"]:
            it.era = c["era"]
        if c["year"] and not it.year:
            it.year = c["year"]
        it.tax_v = TAXONOMY_VERSION
    db.session.commit()
    return len(items)


def clean_dailymotion(after_id: int = 0, limit: int = 200) -> dict:
    """Hide Dailymotion videos viewers' country can't play (the player answers 403). Works through
    the catalogue in id order; call again with the returned `next_after` until it is null."""
    from .providers import dailymotion
    batch = (Item.query.filter(Item.source == "dailymotion", Item.hidden.is_(False), Item.id > after_id)
             .order_by(Item.id).limit(limit).all())
    bad = dailymotion.unplayable([i.external_id for i in batch])
    for i in batch:
        if i.external_id in bad:
            i.hidden = True
    db.session.commit()
    return {"checked": len(batch), "hidden": len(bad),
            "next_after": batch[-1].id if len(batch) == limit else None}