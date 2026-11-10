"""The opp.tik.dot "For You" ranker.

A small, explainable version of what TikTok, Reels and Shorts do, sized for one
Postgres database and a serverless function (no GPU, no feature store). Every
request re-reads the user's latest behaviour, so the next page already reflects
the video they watched ten seconds ago.

Where each piece comes from
---------------------------
1. Watch-based reward per impression. TikTok's leaked "Algo 101" scores a video as
   Plike*Vlike + Pcomment*Vcomment + Eplaytime*Vplaytime + Pplay*Vplay: watch time
   and completion dominate, explicit actions add on top. We log watch time, length,
   loops, unmute and rewind for every card shown, and turn them into one engagement
   value per view (`engagement`).
2. Duration debiasing. Kuaishou's D2Q paper (KDD'22, arXiv:2206.06003) shows raw
   watch time favours long videos and raw completion favours short ones. We judge
   completion against a per-duration-bucket baseline, so a 20s clip watched twice
   and a 9-minute film watched for 3 minutes can both count as "loved".
3. Real-time interest with decay. ByteDance's Monolith (arXiv:2209.07663) trains
   online because interests shift within a session. We do the cheap equivalent: an
   exponentially decayed affinity per feature (topic, culture, channel, era, source,
   uploader) with a 72h half-life, and a 2x boost for the last 45 minutes.
4. Shrinkage. Affinities are Bayesian averages (prior strength 3) so one like
   doesn't flood the feed with a single topic.
5. Exploration. LinUCB / Thompson-sampling bandits (Li et al., WWW'10, arXiv:1003.0146):
   item quality is sampled from a Gaussian posterior whose width shrinks with views,
   so new and rarely-seen items get a fair trial instead of starving.
6. Multi-source candidates, then rank, then re-rank for diversity, the way Twitter's
   open-sourced pipeline (github.com/twitter/the-algorithm) mixes candidate sources
   and enforces author diversity. Candidate pools: taste, popular, fresh, random.
   Re-ranking is MMR-style (Carbonell & Goldstein, SIGIR'98): penalise similarity to
   the last few picks, and reserve every 4th slot for exploration.
"""

import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_

from .extensions import db
from .models import Interaction, Item
from .taxonomy import token_label

HALF_LIFE_H = 72          # long-term interest half-life
SESSION_MIN = 45          # "right now" interest window, weighted x2
PRIOR_STRENGTH = 3.0      # affinity shrinkage
HISTORY = 600             # events read per request
EXPLORE_EVERY = 4         # every 4th slot explores
DIVERSITY = 1.0           # MMR lambda
SEEN_HALF_LIFE_H = 48

# Expected completion ratio by video length (seconds). Tunable; see D2Q.
DURATION_BASELINE = [(30, 0.65), (90, 0.45), (240, 0.32), (600, 0.2), (10**9, 0.08)]

ACTION_REWARD = {"like": 1.2, "save": 1.4, "share": 1.2, "hide": -2.5, "view": 0.3, "skip": -0.5}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def baseline(duration_s: float) -> float:
    for limit, b in DURATION_BASELINE:
        if duration_s <= limit:
            return b
    return 0.08


def engagement(watch_ms: float, duration_s: float | None, loops: int = 0, unmuted: bool = False,
               rewind: bool = False) -> float:
    """One number per impression, roughly -1 (swiped away) .. 2 (watched twice with sound)."""
    w = max(0.0, float(watch_ms or 0)) / 1000
    if w < 2:
        return -0.6                                   # quick skip: the strongest negative signal
    d = float(duration_s or 0)
    completion = min(w / d, 3.0) if d > 1 else min(w / 45, 2.0)
    b = baseline(d or 60)
    rel = _clamp((completion - b) / max(b, 0.1), -1, 2) * 0.5   # relative to what's normal for this length
    absolute = min(1.0, math.log1p(w) / math.log1p(90))         # plain dwell time still matters
    e = 0.55 * rel + 0.35 * absolute + 0.15 * min(int(loops or 0), 2)
    if unmuted:
        e += 0.35                                     # turned the sound on: real interest
    if rewind:
        e += 0.15                                     # chose to come back to it
    return round(_clamp(e, -1, 2), 3)


def item_tokens(labels, era, source, author) -> list[str]:
    toks = [t for t in (labels or "").strip("|").split("|") if t]
    toks += [f"e:{era}", f"s:{source}"]
    if author:
        toks.append("a:" + author.strip().lower()[:60])
    return toks


def _tw(tok: str) -> float:
    return 0.6 if tok[:2] in ("e:", "s:") else 1.0


def _aware(ts):
    if ts is None:
        return datetime.now(timezone.utc)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def profile(user_id: int, now=None):
    """-> (affinity per token, {item_id: last_seen}, hidden ids)"""
    now = now or datetime.now(timezone.utc)
    rows = (db.session.query(Interaction.item_id, Interaction.action, Interaction.value, Interaction.created_at,
                             Item.labels, Item.era, Item.source, Item.author)
            .join(Item, Item.id == Interaction.item_id)
            .filter(Interaction.user_id == user_id)
            .order_by(Interaction.id.desc()).limit(HISTORY).all())
    num, den = defaultdict(float), defaultdict(float)
    seen = {}
    for item_id, action, value, ts, labels, era, source, author in rows:
        ts = _aware(ts)
        if action in ("impression", "view"):
            seen.setdefault(item_id, ts)
        r = value if action == "impression" else ACTION_REWARD.get(action)
        if r is None:
            continue
        age_h = max(0.0, (now - ts).total_seconds() / 3600)
        w = 0.5 ** (age_h / HALF_LIFE_H)
        if age_h * 60 < SESSION_MIN:
            w *= 2.0
        for t in item_tokens(labels, era, source, author):
            wt = w * _tw(t)
            num[t] += wt * r
            den[t] += wt
    aff = {t: num[t] / (den[t] + PRIOR_STRENGTH) for t in num}
    hidden = {i for (i,) in db.session.query(Interaction.item_id)
              .filter(Interaction.user_id == user_id, Interaction.action == "hide")}
    # Older views beyond HISTORY still count as "seen" for a week.
    week = now - timedelta(days=7)
    for item_id, ts in (db.session.query(Interaction.item_id, func.max(Interaction.created_at))
                        .filter(Interaction.user_id == user_id, Interaction.action.in_(["impression", "view"]),
                                Interaction.created_at >= week)
                        .group_by(Interaction.item_id).limit(3000)):
        seen.setdefault(item_id, _aware(ts))
    return aff, seen, hidden


def playable(query):
    """Hide items we know can't play: archive items with no MP4, repeatedly broken ones."""
    return query.filter(Item.hidden.is_(False), Item.broken < 3,
                        or_(Item.media_url.is_(None), Item.media_url != ""))


def _candidates(base, aff, exclude, follows=()):
    q = base.filter(~Item.id.in_(exclude)) if exclude else base
    pools = {}
    if follows:
        authors = list({k.split("|", 1)[1] for k in follows if "|" in k})[:200]
        pools["follow"] = q.filter(func.lower(Item.author).in_(authors)).order_by(func.random()).limit(120).all()
    top = [t for t, v in sorted(aff.items(), key=lambda kv: -kv[1]) if v > 0.05][:6]
    label_toks = [t for t in top if t[:2] in ("t:", "r:", "c:")]
    conds = [Item.labels.like(f"%|{t}|%") for t in label_toks]
    conds += [Item.era == t[2:] for t in top if t.startswith("e:")]
    conds += [func.lower(Item.author) == t[2:] for t in top if t.startswith("a:")]
    if conds:
        pools["taste"] = q.filter(or_(*conds)).order_by(func.random()).limit(220).all()
    pools["popular"] = (q.order_by(((Item.engagement + 0.3 * Item.likes_count) / (Item.impressions + 5)).desc())
                        .limit(150).all())
    pools["fresh"] = q.filter(Item.impressions < 15).order_by(Item.created_at.desc()).limit(150).all()
    pools["random"] = q.order_by(func.random()).limit(220).all()
    out, source_of = {}, {}
    for name, items in pools.items():
        for it in items:
            if it.id not in out:
                out[it.id] = it
                source_of[it.id] = name
    return list(out.values()), source_of


def _sim(a: Item, b: Item) -> float:
    s = 0.0
    if a.author and a.author == b.author:
        s += 0.6
    if a.category == b.category:
        s += 0.35
    ca = {t for t in (a.labels or "").split("|") if t.startswith("c:")}
    if ca and ca & {t for t in (b.labels or "").split("|") if t.startswith("c:")}:
        s += 0.3
    if a.source == b.source:
        s += 0.1
    if a.era == b.era:
        s += 0.05
    return s


FOLLOW_AFFINITY = 0.55   # a followed creator counts like a strong, steady taste signal
FOLLOW_BONUS = 0.35      # ...and gets a flat lift, so they show up often (MMR still spaces them out)


# v9: sources that start fast on weak connections (Lebanon / Middle East first).
# YouTube streams from Google's own servers close to the viewer; plain Archive MP4s come from
# a single US server; third-party iframes boot a whole page.
FAST_SOURCE = {"youtube": 0.1, "tiktok": 0.04}
SLOW_ON_WEAK = {"archive": -0.12, "dailymotion": -0.06, "facebook": -0.08, "instagram": -0.05, "x": -0.05}


def length_fit(d, clip_len=0):
    """Preference by video length. With clips on (30/60/120 s), long videos cost nothing extra
    (only the clip is played), and videos that fit in one clip get a small lift."""
    if not d:
        return 0
    if clip_len:
        return 0.12 if d <= clip_len * 1.25 else 0.04
    return 0.12 if d <= 60 else 0.08 if d <= 180 else 0.03 if d <= 420 else -0.03 if d <= 1200 else -0.1


def rank(user_id: int, base_query, exclude=(), limit=8, seed="", now=None, follows=(), clip_len=0, tier="mid"):
    """-> list of (Item, reason)"""
    now = now or datetime.now(timezone.utc)
    aff, seen, hidden = profile(user_id, now)
    follows = set(follows or ())
    for k in follows:
        if "|" in k:
            t = "a:" + k.split("|", 1)[1]
            aff[t] = max(aff.get(t, 0.0), FOLLOW_AFFINITY)
    exclude = set(exclude) | hidden
    cands, source_of = _candidates(base_query, aff, exclude, follows)
    if not cands:
        return []
    rng = random.Random(f"{user_id}:{seed}:{len(exclude)}")

    scored = []
    for it in cands:
        toks = item_tokens(it.labels or f"|t:{it.category}|", it.era, it.source, it.author)
        contrib = [(aff.get(t, 0.0) * _tw(t), t) for t in toks]
        pers = sum(c for c, _ in contrib) / math.sqrt(len(toks))
        n = it.impressions or 0
        prior = 0.15 + 0.2 * (it.score or 0.5)
        mean = ((it.engagement or 0) + prior * 5) / (n + 5)
        std = 0.6 / math.sqrt(n + 1)
        q = mean + std * rng.gauss(0, 1)                       # Thompson sample
        dur = length_fit(it.duration, clip_len)
        s = pers + 0.7 * q + 0.15 * (it.score or 0) + dur + 0.05 * math.log1p(it.likes_count or 0)
        s -= 0.3 * min(it.broken or 0, 3)
        fast_copy = bool((it.media_info or {}).get("hls") or (it.media_info or {}).get("clip"))
        if fast_copy:
            s += 0.15   # v11: a small hosted copy starts instantly; lean the feed towards them
        if tier != "high":
            s += FAST_SOURCE.get(it.source, 0) + (0 if fast_copy else SLOW_ON_WEAK.get(it.source, 0) * (1.5 if tier == "low" else 1))
        if it.source == "archive" and it.media_url is None:
            s -= 0.25   # not resolved yet: would cost the feed request a lookup on archive.org
        if it.id in seen:
            age_h = (now - seen[it.id]).total_seconds() / 3600
            s -= 0.8 * 0.5 ** (age_h / SEEN_HALF_LIFE_H)
        best = max(contrib, default=(0, None))
        reason = None
        followed = bool(it.author) and f"{it.source}|{it.author.strip().lower()[:60]}" in follows
        if followed:
            s += FOLLOW_BONUS
            reason = f"From {it.author}, who you follow"
        elif best[0] > 0.12 and best[1] and best[1][:2] in ("t:", "r:", "c:"):
            reason = f"Because you watch {token_label(best[1])}"
        elif source_of.get(it.id) == "popular" and n >= 5:
            reason = "Popular on opp.tik.dot"
        scored.append({"item": it, "s": s, "std": std, "reason": reason, "seen": it.id in seen})
    scored.sort(key=lambda x: -x["s"])

    picked = []
    pool = scored
    for slot in range(limit):
        if not pool:
            break
        explore = slot % EXPLORE_EVERY == EXPLORE_EVERY - 1
        if explore:
            options = [x for x in pool if x["std"] > 0.3 and not x["seen"]]
            if options:
                choice = max(options[:60], key=lambda x: x["std"] + rng.random() * 0.5)
                choice = {**choice, "reason": "Something new"}
            else:
                explore = False
        if not explore:
            recent = [p["item"] for p in picked[-4:]]
            choice = max(pool[:50], key=lambda x: x["s"] - DIVERSITY * sum(_sim(x["item"], r) for r in recent) / 2)
        picked.append(choice)
        pool = [x for x in pool if x["item"].id != choice["item"].id]
    return [(p["item"], p["reason"]) for p in picked]
