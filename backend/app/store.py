from flask import current_app
from sqlalchemy.exc import IntegrityError

from .classifier import classify
from .extensions import db
from .models import Item


def upsert_items(raw_items, hint_era=None, hint_category=None, force=False) -> list[Item]:
    """Classify raw provider dicts and store the nostalgic ones.
    Existing items are returned untouched. `force` keeps items the classifier
    rejects (used when an admin hand-picks a TikTok)."""
    max_year = current_app.config["MAX_YEAR"]
    out: list[Item] = []
    for r in raw_items:
        if not r.get("external_id"):
            continue
        existing = Item.query.filter_by(source=r["source"], external_id=r["external_id"]).first()
        if existing:
            out.append(existing)
            continue
        c = classify(r.get("title"), r.get("description"), r.get("tags"), r.get("year"),
                     hint_era=hint_era, hint_category=hint_category, max_year=max_year)
        if not c["accepted"] and not force:
            continue
        item = Item(
            source=r["source"], external_id=r["external_id"], kind=r.get("kind", "video"),
            url=r["url"], title=r.get("title") or "", author=r.get("author"),
            description=r.get("description"), thumbnail=r.get("thumbnail"),
            era=c["era"] or hint_era or "00s", year=c["year"],
            category=c["category"] if c["category"] != "culture" or not hint_category else hint_category,
            tags=c["tags"], score=max(c["score"], 0.5 if force else 0),
        )
        try:
            with db.session.begin_nested():
                db.session.add(item)
            out.append(item)
        except IntegrityError:  # inserted concurrently by another worker
            dup = Item.query.filter_by(source=r["source"], external_id=r["external_id"]).first()
            if dup:
                out.append(dup)
    db.session.commit()
    return out
