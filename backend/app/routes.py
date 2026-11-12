import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import or_

from .auth import admin_required, login_required
from .extensions import db
from .ingest import ingest_urls, run as run_ingest
from .models import SOURCE_LABELS, SOURCES, Interaction, Item
from .providers import archive, dailymotion, youtube
from .ranking import engagement, playable, rank
from .store import reclassify, resolve_backlog, resolve_media, upsert_items
from .taxonomy import CHANNEL_IDS, ERA_RANGES, ERAS, REGION_IDS, TOPIC_IDS, meta as taxonomy_meta

log = logging.getLogger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")

ERA_QUERY_SUFFIX = {"50s": "1950s", "60s": "1960s", "70s": "70s", "80s": "80s", "90s": "90s", "00s": "2000s"}
DEFINITIVE_ERRORS = {"yt:2", "yt:100", "yt:101", "yt:150", "media:4"}  # removed / not embeddable / no file
DIMENSIONS = {"era": ERAS, "topic": TOPIC_IDS, "region": REGION_IDS, "channel": CHANNEL_IDS, "source": SOURCES}


# ---------- helpers ----------

def _list(raw, allowed):
    if isinstance(raw, str):
        raw = raw.split(",")
    vals = [str(v) for v in (raw or []) if v]
    return [v for v in dict.fromkeys(vals) if v in allowed]


def parse_filters(src=None) -> dict:
    """Filters from query string or JSON body. `category` is the v3 name of `topic`;
    v3's `classic` era expands to every decade before the '90s."""
    src = src if src is not None else request.args
    out = {}
    for dim, allowed in DIMENSIONS.items():
        raw = src.get(dim) or (src.get("category") if dim == "topic" else None) or []
        if dim == "era":
            raw = raw.split(",") if isinstance(raw, str) else list(raw)
            if "classic" in raw:
                raw = [e for e in raw if e != "classic"] + ["50s", "60s", "70s", "80s"]
        out[dim] = _list(raw, allowed)
    return out


def _labels_any(prefix, values):
    return or_(*[Item.labels.like(f"%|{prefix}:{v}|%") for v in values])


def apply_filters(query, f: dict):
    """OR inside a dimension, AND across dimensions."""
    if f.get("era"):
        query = query.filter(Item.era.in_(f["era"]))
    if f.get("topic"):
        query = query.filter(or_(_labels_any("t", f["topic"]), Item.category.in_(f["topic"])))
    if f.get("region"):
        query = query.filter(_labels_any("r", f["region"]))
    if f.get("channel"):
        query = query.filter(_labels_any("c", f["channel"]))
    if f.get("source"):
        query = query.filter(Item.source.in_(f["source"]))
    return query


def _serialize(items, user_id, reasons=None):
    if not items:
        return []
    ids = [i.id for i in items]
    rows = db.session.query(Interaction.item_id, Interaction.action).filter(
        Interaction.user_id == user_id, Interaction.item_id.in_(ids),
        Interaction.action.in_(["like", "save"])).all()
    flags = defaultdict(set)
    for item_id, action in rows:
        flags[item_id].add(action)
    out = []
    for i in items:
        d = i.to_dict(liked="like" in flags[i.id], saved="save" in flags[i.id])
        if reasons and reasons.get(i.id):
            d["reason"] = reasons[i.id]
        out.append(d)
    return out


def _enabled_sources():
    c = current_app.config
    return {
        "youtube": bool(c["YOUTUBE_API_KEY"]), "archive": True, "dailymotion": c["DAILYMOTION"],
        "tiktok": True, "instagram": bool(c["META_ACCESS_TOKEN"] and c["IG_USER_ID"]),
        "facebook": True, "x": bool(c["X_BEARER_TOKEN"]), "reddit": bool(c["REDDIT_CLIENT_ID"]),
    }


# ---------- public ----------

@bp.get("/health")
def health():
    return jsonify(ok=True)


def _edge_cache(resp, seconds=300):
    """Same answer for everyone: let Vercel's CDN serve it, so the app boots without waiting
    for a (possibly cold) Python function."""
    resp.headers["Cache-Control"] = f"public, max-age=60, s-maxage={seconds}, stale-while-revalidate=86400"
    return resp


@bp.get("/meta")
def meta():
    m = taxonomy_meta()
    enabled = _enabled_sources()
    used = {s for (s,) in db.session.query(Item.source).distinct()} if _db_ok() else set()
    return _edge_cache(jsonify(
        google_client_id=current_app.config["GOOGLE_CLIENT_ID"],
        dev_login=current_app.config["DEV_LOGIN"],
        dm_player=current_app.config["DM_PLAYER_ID"] if current_app.config["DM_PLAYER_ID"].isalnum() else "",
        sponsor=_sponsor(),
        sources=[{"id": s, "label": SOURCE_LABELS[s], "enabled": enabled.get(s, False)}
                 for s in SOURCES if s in used or enabled.get(s) and s not in ("facebook", "reddit")],
        # v3 clients read `categories`
        categories=m["topics"],
        **m,
    ))


def _sponsor():
    """The "Sponsored" box on the loading card (env SPONSOR_*). Links and images: https only."""
    c = current_app.config
    https = lambda u: u if u.startswith("https://") else ""  # noqa: E731
    s = {"title": c["SPONSOR_TITLE"][:60], "text": c["SPONSOR_TEXT"][:120],
         "url": https(c["SPONSOR_URL"]), "image": https(c["SPONSOR_IMAGE"])}
    return s if any(s.values()) else None


def _db_ok():
    try:
        db.session.execute(db.select(Item.id).limit(1))
        return True
    except Exception:
        db.session.rollback()
        return False


@bp.get("/preview")
def preview():
    """Thumbnail wall for the sign-in page."""
    items = (Item.query.filter(Item.hidden.is_(False), Item.thumbnail.isnot(None))
             .order_by(Item.score.desc(), Item.id.desc()).limit(18).all())
    return _edge_cache(jsonify(items=[{"id": i.id, "thumbnail": i.thumbnail, "era_label": i.to_dict()["era_label"]}
                                      for i in items]), 900)


# ---------- feed ----------

def _fast(it) -> bool:
    """Starts quickly on a weak link: YouTube (nearby servers) or a small hosted clip."""
    return it.kind == "image" or it.source == "youtube" or bool((it.media_info or {}).get("clip"))


@bp.route("/feed", methods=["GET", "POST"])
@login_required
def feed():
    body = request.get_json(silent=True) or {} if request.method == "POST" else {}
    src = body or request.args
    f = parse_filters(src)
    limit = max(1, min(int(src.get("limit", 8) or 8), 20))
    seed = str(src.get("seed", ""))[:32]
    exclude = src.get("exclude") or []
    if isinstance(exclude, str):
        exclude = exclude.split(",")
    exclude = {int(x) for x in list(exclude)[:400] if str(x).isdigit()}

    base = apply_filters(playable(Item.query), f)
    follows = follow_keys(g.user)
    try:
        clip_len = int(src.get("len", 0) or 0)
    except (TypeError, ValueError):
        clip_len = 0
    clip_len = clip_len if clip_len in (30, 60, 120) else 0
    tier = str(src.get("tier") or "mid")
    tier = tier if tier in ("low", "mid", "high") else "mid"
    picked = rank(g.user.id, base, exclude=exclude, limit=limit + 4, seed=seed, follows=follows,
                  clip_len=clip_len, tier=tier)
    ran_out = len(picked) < limit

    # Archive items nobody has resolved yet: look up at most a few, with a short timeout, so
    # this request never waits long on archive.org (v5 could block the feed for 4s+ here).
    # Whatever is still unknown is skipped for this page and resolved by the cron.
    unknown = [it for it, _ in picked if it.source == "archive" and it.media_url is None][:4]
    if unknown:
        resolve_media(unknown, timeout=2)
    picked = [(it, r) for it, r in picked
              if not it.hidden and it.media_url != "" and not (it.source == "archive" and it.media_url is None)][:limit]

    # v9: the very first video of a session must start instantly: put a fast-starting one first.
    if not exclude and picked and not _fast(picked[0][0]):
        k = next((i for i, (it, _) in enumerate(picked[:6]) if _fast(it)), None)
        if k:
            picked.insert(0, picked.pop(k))

    items = [it for it, _ in picked]
    reasons = {it.id: r for it, r in picked}
    done = ran_out and len(items) < limit
    return jsonify(items=_serialize(items, g.user.id, reasons), done=done,
                   next_cursor=None if done else len(exclude) + len(items))


@bp.get("/feed/count")
@login_required
def feed_count():
    return jsonify(count=apply_filters(playable(Item.query), parse_filters()).count())


@bp.post("/events")
@login_required
def events():
    """Batched watch events from the player (sent with navigator.sendBeacon)."""
    body = request.get_json(silent=True, force=True) or {}
    evs = [e for e in (body.get("events") or [])[:60] if isinstance(e, dict) and str(e.get("item_id", "")).isdigit()]
    items = {i.id: i for i in Item.query.filter(Item.id.in_({int(e["item_id"]) for e in evs}))} if evs else {}
    uid = g.user.id
    for e in evs:
        it = items.get(int(e["item_id"]))
        if not it:
            continue
        kind = e.get("type")
        if kind == "impression":
            dur_ms = float(e.get("duration_ms") or 0)
            if dur_ms > 1000 and not it.duration and not (it.media_info or {}).get("clip"):   # a hosted clip's length isn't the video's
                it.duration = int(dur_ms / 1000)  # learn lengths from the player
            # v9: a clip is judged against the clip's length, not the whole video's.
            clip_s = float(e.get("clip_ms") or 0) / 1000
            offered = clip_s if clip_s > 1 else (dur_ms / 1000 if dur_ms else it.duration)
            v = engagement(e.get("watch_ms"), offered, e.get("loops", 0),
                           bool(e.get("unmuted")), bool(e.get("rewind")))
            db.session.add(Interaction(user_id=uid, item_id=it.id, action="impression", value=v))
            it.impressions = (it.impressions or 0) + 1
            it.engagement = (it.engagement or 0) + v
        elif kind == "broken":
            code = str(e.get("code") or "")[:20]
            # v13: a Dailymotion stall / player error is usually our borrowed player or the
            # viewer's network, not the video. Don't let it hide the video for everyone.
            if code == "crash" or (it.source == "dailymotion" and code.startswith("dm:")):
                continue
            it.broken = (it.broken or 0) + 1
            if code in DEFINITIVE_ERRORS:
                it.hidden = True
            if code.startswith("media") and it.source == "archive" and it.broken >= 2:
                it.media_url = None  # re-resolve next time (the file may have moved)
    db.session.commit()
    return jsonify(ok=True, n=len(evs))


# ---------- search ----------

@bp.get("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()[:100]
    if not q:
        return jsonify(items=[], live=0)
    f = parse_filters()
    like = f"%{q}%"
    found = (apply_filters(playable(Item.query), f)
             .filter(or_(Item.title.ilike(like), Item.author.ilike(like), Item.description.ilike(like),
                         Item.labels.ilike(like)))
             .order_by(Item.score.desc(), Item.impressions.desc()).limit(40).all())

    live_added = 0
    if len(found) < 12 and request.args.get("live", "1") != "0":
        eras = f["era"]
        hint = eras[0] if len(eras) == 1 else None
        has_era_word = any(w in q.lower() for w in ("19", "200", "y2k", "retro", "vintage", "old", "قديم", "زمان",
                                                    "80", "90", "70", "60"))
        era_q = q if has_era_word else f"{q} {ERA_QUERY_SUFFIX.get(hint, '90s')}"
        y0, y1 = ERA_RANGES.get(hint, (1930, current_app.config["MAX_YEAR"]))
        y1 = min(y1, current_app.config["MAX_YEAR"])
        terms = archive.safe_terms(q)
        jobs = []
        if current_app.config["YOUTUBE_API_KEY"]:
            jobs.append(lambda: youtube.search(current_app.config["YOUTUBE_API_KEY"], era_q, 12))
        if terms:
            jobs.append(lambda: archive.search(f"title:({terms}) OR subject:({terms})", rows=12,
                                               year_from=y0, year_to=y1))
        if current_app.config["DAILYMOTION"]:
            jobs.append(lambda: dailymotion.search(era_q, 12))
        app = current_app._get_current_object()

        def run(job):
            with app.app_context():
                try:
                    return job()
                except Exception as e:
                    log.warning("live search failed: %s", e)
                    return []

        raw = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            for res in pool.map(run, jobs):
                raw += res
        new = [i for i in upsert_items(raw, hint_era=hint) if not i.hidden and i.media_url != ""]
        new = apply_filters(Item.query.filter(Item.id.in_([i.id for i in new])), f).all() if new else []
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
    resolve_media([item], timeout=5)
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
    f = parse_filters(body)
    keep = {k: v for k, v in (g.user.prefs or {}).items() if k in ("follows", "quality")}
    g.user.prefs = {**keep, **f, "category": f["topic"], "reverse": bool(body.get("reverse", False))}
    db.session.commit()
    return jsonify(user=g.user.to_dict(current_app.config["ADMIN_EMAILS"]))


def follow_keys(user) -> set[str]:
    """Followed creators as "source|author lowercased"."""
    return {str(k) for k in ((user.prefs or {}).get("follows") or [])}


@bp.post("/me/follow")
@login_required
def follow():
    """Follow / unfollow a creator (channel, uploader). Followed creators get their own
    candidate pool and a boost in the ranking."""
    body = request.get_json(silent=True) or {}
    author = str(body.get("author") or "").strip().lower()[:60]
    source = str(body.get("source") or "")
    if not author or source not in SOURCES:
        return jsonify(error="author and source required"), 400
    key = f"{source}|{author}"
    prefs = dict(g.user.prefs or {})
    follows = [k for k in (prefs.get("follows") or []) if k != key]
    if body.get("on", True):
        follows.insert(0, key)
    prefs["follows"] = follows[:500]
    g.user.prefs = prefs
    db.session.commit()
    return jsonify(user=g.user.to_dict(current_app.config["ADMIN_EMAILS"]), following=bool(body.get("on", True)))


# ---------- admin & cron ----------

@bp.post("/admin/links")
@bp.post("/admin/tiktok")
@admin_required
def admin_links():
    body = request.get_json(silent=True) or {}
    urls = [u for u in body.get("urls", []) if isinstance(u, str)][:50]
    era = body.get("era") if body.get("era") in ERAS else None
    topic = body.get("topic") if body.get("topic") in TOPIC_IDS else None
    region = body.get("region") if body.get("region") in REGION_IDS else None
    items = ingest_urls(urls, force=True, hint_era=era, hint_topic=topic, hint_region=region)
    return jsonify(added=len(items), items=_serialize(items, g.user.id))


@bp.post("/admin/ingest")
@admin_required
def admin_ingest():
    return jsonify(stats=run_ingest(max_queries=12, per_query=15, budget_s=40))


@bp.post("/admin/reclassify")
@admin_required
def admin_reclassify():
    return jsonify(relabelled=reclassify(limit=5000))


@bp.post("/admin/dm-clean")
@admin_required
def admin_dm_clean():
    """Hide Dailymotion videos blocked in Lebanon / not embeddable. Repeat with ?after=<next_after>."""
    from .store import clean_dailymotion
    return jsonify(clean_dailymotion(after_id=request.args.get("after", 0, type=int)))


@bp.post("/admin/archive-upgrade")
@admin_required
def admin_archive_upgrade():
    """Re-read Archive items stored by v5 or older so they get every rendition + the direct
    storage server (faster start, data-saver quality). Bounded to fit a serverless call."""
    n = resolve_backlog(20, upgrade=160, timeout=5)
    left = Item.query.filter(Item.source == "archive", Item.media_url.isnot(None), Item.media_url != "",
                             Item.media_info.is_(None)).count()
    return jsonify(upgraded=n, remaining=left)


@bp.get("/admin/stats")
@admin_required
def admin_stats():
    rows = db.session.query(Item.source, Item.era, db.func.count(Item.id)).group_by(Item.source, Item.era).all()
    unresolved = Item.query.filter(Item.source == "archive", Item.media_url.is_(None)).count()
    legacy = Item.query.filter(Item.source == "archive", Item.media_url.isnot(None), Item.media_url != "",
                               Item.media_info.is_(None)).count()
    return jsonify(total=Item.query.count(), unresolved_archive=unresolved, legacy_archive=legacy,
                   sources=_enabled_sources(),
                   breakdown=[{"source": s, "era": e, "count": c} for s, e, c in rows])


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
    if body.get("category") in TOPIC_IDS:
        item.category = body["category"]
    db.session.commit()
    return jsonify(item=item.to_dict())


@bp.get("/cron/ingest")
def cron_ingest():
    secret = current_app.config["CRON_SECRET"]
    if not secret or request.headers.get("Authorization") != f"Bearer {secret}":
        return jsonify(error="Unauthorized"), 401
    # Bounded so it finishes inside a serverless time limit.
    return jsonify(stats=run_ingest(max_queries=14, per_query=12, budget_s=45))