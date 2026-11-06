import hashlib
import logging
from collections import defaultdict

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import or_

from .auth import admin_required, login_required
from .extensions import db
from .ingest import ingest_tiktok_urls, run as run_ingest
from .models import (CATEGORIES, CATEGORY_LABELS, ERA_LABELS, ERAS, SOURCE_LABELS, SOURCES,
                     Interaction, Item)
from .providers import archive, youtube
from .store import upsert_items

log = logging.getLogger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")

CANDIDATE_POOL = 600
ERA_QUERY_SUFFIX = {"classic": "80s", "90s": "90s", "00s": "2000s"}
ACTION_WEIGHTS = {"like": 1.0, "save": 1.2, "share": 0.8, "view": 0.1, "skip": -0.4, "hide": -1.5}


# ---------- helpers ----------

def _csv(name, allowed):
    vals = [v for v in (request.args.get(name) or "").split(",") if v]
    return [v for v in vals if v in allowed]


def _filtered(query):
    query = query.filter(Item.hidden.is_(False))
    if eras := _csv("era", ERAS):
        query = query.filter(Item.era.in_(eras))
    if cats := _csv("category", CATEGORIES):
        query = query.filter(Item.category.in_(cats))
    if srcs := _csv("source", SOURCES):
        query = query.filter(Item.source.in_(srcs))
    return query


def _serialize(items, user_id):
    if not items:
        return []
    ids = [i.id for i in items]
    rows = db.session.query(Interaction.item_id, Interaction.action).filter(
        Interaction.user_id == user_id, Interaction.item_id.in_(ids),
        Interaction.action.in_(["like", "save"])).all()
    flags = defaultdict(set)
    for item_id, action in rows:
        flags[item_id].add(action)
    return [i.to_dict(liked="like" in flags[i.id], saved="save" in flags[i.id]) for i in items]


def _affinity(user_id):
    """Per-category and per-era taste weights from the user's recent behaviour."""
    rows = (db.session.query(Item.category, Item.era, Interaction.action)
            .join(Item, Item.id == Interaction.item_id)
            .filter(Interaction.user_id == user_id)
            .order_by(Interaction.id.desc()).limit(500).all())
    cat, era = defaultdict(float), defaultdict(float)
    for c, e, a in rows:
        w = ACTION_WEIGHTS.get(a, 0)
        cat[c] += w
        era[e] += w
    norm = lambda d: {k: max(-0.5, min(0.5, v / 10)) for k, v in d.items()}
    return norm(cat), norm(era)


def _jitter(seed, item_id):
    h = hashlib.md5(f"{seed}:{item_id}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


# ---------- public ----------

@bp.get("/health")
def health():
    return jsonify(ok=True)


@bp.get("/meta")
def meta():
    return jsonify(
        google_client_id=current_app.config["GOOGLE_CLIENT_ID"],
        dev_login=current_app.config["DEV_LOGIN"],
        eras=[{"id": e, "label": ERA_LABELS[e]} for e in ERAS],
        categories=[{"id": c, "label": CATEGORY_LABELS[c]} for c in CATEGORIES],
        sources=[{"id": s, "label": SOURCE_LABELS[s]} for s in SOURCES],
    )


@bp.get("/preview")
def preview():
    """Thumbnail wall for the sign-in page."""
    items = (Item.query.filter(Item.hidden.is_(False), Item.thumbnail.isnot(None))
             .order_by(Item.score.desc(), Item.id.desc()).limit(18).all())
    return jsonify(items=[{"id": i.id, "thumbnail": i.thumbnail, "era_label": ERA_LABELS[i.era]}
                          for i in items])


# ---------- feed ----------

@bp.get("/feed")
@login_required
def feed():
    uid = g.user.id
    limit = max(1, min(int(request.args.get("limit", 8)), 20))
    offset = max(0, int(request.args.get("cursor") or 0))
    seed = request.args.get("seed", "")[:32]

    hidden_ids = db.session.query(Interaction.item_id).filter(
        Interaction.user_id == uid, Interaction.action == "hide")
    candidates = (_filtered(Item.query).filter(~Item.id.in_(hidden_ids))
                  .order_by(Item.score.desc(), Item.id.desc()).limit(CANDIDATE_POOL).all())

    cat_aff, era_aff = _affinity(uid)
    viewed = {r[0] for r in db.session.query(Interaction.item_id).filter(
        Interaction.user_id == uid, Interaction.action == "view")}

    def rank(i):
        return (i.score
                + 0.15 * min(i.likes_count, 20) / 20
                + cat_aff.get(i.category, 0) + era_aff.get(i.era, 0)
                - (0.45 if i.id in viewed else 0)
                + 0.6 * _jitter(seed, i.id))

    ranked = sorted(candidates, key=rank, reverse=True)
    page = ranked[offset:offset + limit]
    nxt = offset + limit if offset + limit < len(ranked) else None
    return jsonify(items=_serialize(page, uid), next_cursor=nxt)


# ---------- search ----------

@bp.get("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()[:100]
    if not q:
        return jsonify(items=[], live=0)
    like = f"%{q}%"
    found = (_filtered(Item.query)
             .filter(or_(Item.title.ilike(like), Item.author.ilike(like), Item.description.ilike(like)))
             .order_by(Item.score.desc()).limit(40).all())

    live_added = 0
    if len(found) < 12 and request.args.get("live", "1") != "0":
        eras = _csv("era", ERAS)
        hint = eras[0] if len(eras) == 1 else None
        has_era_word = any(w in q.lower() for w in ("80", "90", "200", "y2k", "retro", "vintage"))
        yt_query = q if has_era_word else f"{q} {ERA_QUERY_SUFFIX.get(hint, 'retro 90s')}"
        raw = []
        try:
            raw += youtube.search(current_app.config["YOUTUBE_API_KEY"], yt_query, 12)
        except Exception as e:
            log.warning("live youtube search failed: %s", e)
        try:
            terms = archive.safe_terms(q)
            if terms:
                y0, y1 = {"classic": (1950, 1989), "90s": (1990, 1999), "00s": (2000, 2009)}.get(
                    hint, (1950, current_app.config["MAX_YEAR"]))
                raw += archive.search(f"title:({terms}) OR subject:({terms})", rows=12,
                                      year_from=y0, year_to=y1)
        except Exception as e:
            log.warning("live archive search failed: %s", e)
        new = [i for i in upsert_items(raw, hint_era=hint) if not i.hidden]
        if eras:
            new = [i for i in new if i.era in eras]
        seen = {i.id for i in found}
        for i in new:
            if i.id not in seen:
                found.append(i)
                seen.add(i.id)
                live_added += 1
    return jsonify(items=_serialize(found[:60], g.user.id), live=live_added)


# ---------- items & interactions ----------

@bp.get("/items/<int:item_id>")
@login_required
def get_item(item_id):
    item = db.session.get(Item, item_id)
    if not item or item.hidden:
        return jsonify(error="Not found"), 404
    return jsonify(item=_serialize([item], g.user.id)[0])


@bp.post("/items/<int:item_id>/interact")
@login_required
def interact(item_id):
    action = (request.get_json(silent=True) or {}).get("action")
    item = db.session.get(Item, item_id)
    if not item:
        return jsonify(error="Not found"), 404
    uid = g.user.id
    toggles = {"like": "like", "unlike": "like", "save": "save", "unsave": "save"}
    if action in toggles:
        kind = toggles[action]
        row = Interaction.query.filter_by(user_id=uid, item_id=item_id, action=kind).first()
        if action in ("like", "save") and not row:
            db.session.add(Interaction(user_id=uid, item_id=item_id, action=kind))
            if kind == "like":
                item.likes_count += 1
        elif action in ("unlike", "unsave") and row:
            db.session.delete(row)
            if kind == "like":
                item.likes_count = max(0, item.likes_count - 1)
    elif action in ("view", "skip", "hide", "share"):
        db.session.add(Interaction(user_id=uid, item_id=item_id, action=action))
    else:
        return jsonify(error="Unknown action"), 400
    db.session.commit()
    return jsonify(item=_serialize([item], uid)[0])


# ---------- me ----------

@bp.get("/me/collection")
@login_required
def collection():
    kind = request.args.get("type", "like")
    if kind not in ("like", "save"):
        return jsonify(error="type must be like or save"), 400
    items = (Item.query.join(Interaction, Interaction.item_id == Item.id)
             .filter(Interaction.user_id == g.user.id, Interaction.action == kind, Item.hidden.is_(False))
             .order_by(Interaction.id.desc()).limit(120).all())
    return jsonify(items=_serialize(items, g.user.id))


@bp.put("/me/prefs")
@login_required
def save_prefs():
    body = request.get_json(silent=True) or {}
    g.user.prefs = {
        "era": [e for e in body.get("era", []) if e in ERAS],
        "category": [c for c in body.get("category", []) if c in CATEGORIES],
        "reverse": bool(body.get("reverse", False)),
    }
    db.session.commit()
    return jsonify(user=g.user.to_dict(current_app.config["ADMIN_EMAILS"]))


# ---------- admin & cron ----------

@bp.post("/admin/tiktok")
@admin_required
def admin_tiktok():
    urls = [u for u in (request.get_json(silent=True) or {}).get("urls", []) if isinstance(u, str)][:50]
    items = ingest_tiktok_urls(urls, force=True)
    return jsonify(added=len(items), items=_serialize(items, g.user.id))


@bp.post("/admin/ingest")
@admin_required
def admin_ingest():
    return jsonify(stats=run_ingest(max_queries=8))


@bp.get("/admin/stats")
@admin_required
def admin_stats():
    rows = db.session.query(Item.source, Item.era, db.func.count(Item.id)).group_by(Item.source, Item.era).all()
    return jsonify(total=Item.query.count(), breakdown=[{"source": s, "era": e, "count": c} for s, e, c in rows])


@bp.patch("/admin/items/<int:item_id>")
@admin_required
def admin_item(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        return jsonify(error="Not found"), 404
    body = request.get_json(silent=True) or {}
    if "hidden" in body:
        item.hidden = bool(body["hidden"])
    if body.get("era") in ERAS:
        item.era = body["era"]
    if body.get("category") in CATEGORIES:
        item.category = body["category"]
    db.session.commit()
    return jsonify(item=item.to_dict())


@bp.get("/cron/ingest")
def cron_ingest():
    secret = current_app.config["CRON_SECRET"]
    if not secret or request.headers.get("Authorization") != f"Bearer {secret}":
        return jsonify(error="Unauthorized"), 401
    # Small batch so it finishes inside a serverless time limit.
    return jsonify(stats=run_ingest(max_queries=6, per_query=12))
