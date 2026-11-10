from datetime import datetime, timezone

from flask import current_app

from .extensions import db
from .taxonomy import (CHANNEL_LABELS, ERA_LABELS, ERAS, REGION_LABELS, TOPIC_IDS, TOPIC_LABELS,
                       LEGACY_ERAS)


def utcnow():
    return datetime.now(timezone.utc)


# Kept for imports elsewhere; the topic list is the v4 "category" list.
CATEGORIES = TOPIC_IDS
CATEGORY_LABELS = TOPIC_LABELS

SOURCES = ["youtube", "archive", "dailymotion", "tiktok", "instagram", "facebook", "x", "reddit"]
SOURCE_LABELS = {"tiktok": "TikTok", "youtube": "YouTube", "archive": "Internet Archive",
                 "dailymotion": "Dailymotion", "instagram": "Instagram", "facebook": "Facebook",
                 "x": "X", "reddit": "Reddit"}

# Long videos (films, compilations) start a little way in, so the feed lands on the action
# instead of studio logos and black leader. Short clips always start at 0:00.
CLIP_FROM = 360


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    google_sub = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(320), nullable=False)
    name = db.Column(db.String(200))
    avatar = db.Column(db.String(600))
    prefs = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self, admin_emails=()):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "avatar": self.avatar,
            "prefs": self.prefs or {},
            "is_admin": self.email.lower() in admin_emails,
        }


class Item(db.Model):
    __tablename__ = "items"
    __table_args__ = (
        db.UniqueConstraint("source", "external_id", name="uq_item_source_ext"),
        db.Index("ix_items_era_category", "era", "category"),
        db.Index("ix_items_score", "score"),
    )

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(16), nullable=False)
    external_id = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(8), nullable=False, default="video")  # video | image
    url = db.Column(db.String(600), nullable=False)
    title = db.Column(db.String(300), nullable=False, default="")
    author = db.Column(db.String(200))
    description = db.Column(db.Text)
    thumbnail = db.Column(db.String(600))
    era = db.Column(db.String(8), nullable=False)
    year = db.Column(db.Integer)
    category = db.Column(db.String(24), nullable=False, default="culture")  # primary topic
    tags = db.Column(db.JSON, nullable=False, default=list)
    score = db.Column(db.Float, nullable=False, default=0.5)  # nostalgia confidence 0..1
    likes_count = db.Column(db.Integer, nullable=False, default=0)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    # ---- v4
    labels = db.Column(db.String(400), nullable=False, default="")   # "|t:football|r:arabic|c:mbc|"
    lang = db.Column(db.String(16))
    duration = db.Column(db.Integer)                                 # seconds, when known
    # Direct, natively playable file (Internet Archive MP4, X video...). NULL = not resolved yet,
    # "" = resolved and there is nothing playable (kept out of the feed).
    media_url = db.Column(db.String(800))
    impressions = db.Column(db.Integer, nullable=False, default=0)
    engagement = db.Column(db.Float, nullable=False, default=0.0)    # sum of per-view engagement
    broken = db.Column(db.Integer, nullable=False, default=0)        # player error reports
    tax_v = db.Column(db.Integer, nullable=False, default=0)         # taxonomy version of labels
    # ---- v6: every rendition of the clip + the storage server that holds it (Internet Archive).
    # {"node": "ia800308.us.archive.org/21/items/<id>", "r": [[file name, kbps, height], ...]}
    media_info = db.Column(db.JSON)

    def label_list(self, kind):
        return [t[2:] for t in (self.labels or "").strip("|").split("|") if t.startswith(kind + ":")]

    def start_at(self):
        d = self.duration or 0
        return int(min(d * 0.12, 180)) if d > CLIP_FROM else 0

    def renditions(self):
        """Playable files, lowest bitrate first: [{url, fallback, kbps, h}]. The player picks one
        from the viewer's connection; `url` is the direct storage-server link (fastest start),
        `fallback` the archive.org/download/ link that survives the item moving servers."""
        info = self.media_info or {}
        if self.source != "archive" or not info.get("r"):
            return []
        from .providers.archive import download_url, node_url
        node = info.get("node")
        out = []
        for name, kbps, h in info["r"][:4]:
            dl = download_url(self.external_id, name)
            out.append({"url": node_url(node, name) if node else dl, "fallback": dl, "kbps": kbps, "h": h or None})
        return out

    def hosted_clip(self):
        """v11: the small clip made by app/clips.py and served by Cloudflare Pages, if there is one."""
        c = (self.media_info or {}).get("clip")
        try:
            base = current_app.config.get("CLIPS_BASE", "")
        except RuntimeError:
            base = ""
        if not c or not base.startswith("https://"):
            return None
        return {"url": f"{base}/c/{self.id}.mp4?v={c.get('v', 1)}", "s": c.get("s"), "from": c.get("from", 0),
                "whole": bool(c.get("whole"))}

    def to_dict(self, liked=False, saved=False):
        era = LEGACY_ERAS.get(self.era, self.era)
        topics = self.label_list("t") or [self.category]
        return {
            "id": self.id,
            "source": self.source,
            "source_label": SOURCE_LABELS.get(self.source, self.source),
            "external_id": self.external_id,
            "kind": self.kind,
            "url": self.url,
            "media_url": self.media_url or None,
            "renditions": self.renditions(),
            # v7: adaptive HLS on our CDN (archive items only); the player prefers it.
            "hls": (self.media_info or {}).get("hls"),
            "clip": self.hosted_clip(),
            "hls_start": (self.media_info or {}).get("hls_start", 0),
            "title": self.title,
            "author": self.author,
            "thumbnail": self.thumbnail,
            "era": era,
            "era_label": ERA_LABELS.get(era, era),
            "year": self.year,
            "category": topics[0],
            "category_label": TOPIC_LABELS.get(topics[0], topics[0]),
            "topics": [{"id": t, "label": TOPIC_LABELS.get(t, t)} for t in topics],
            "regions": [{"id": r, "label": REGION_LABELS.get(r, r)} for r in self.label_list("r")],
            "channels": [{"id": c, "label": CHANNEL_LABELS.get(c, c)} for c in self.label_list("c")],
            "duration": self.duration,
            "start": self.start_at(),
            "tags": (self.tags or [])[:6],
            "likes": self.likes_count,
            "liked": liked,
            "saved": saved,
        }


class Interaction(db.Model):
    __tablename__ = "interactions"
    __table_args__ = (
        db.Index("ix_interactions_user_action", "user_id", "action"),
        db.Index("ix_interactions_user_item", "user_id", "item_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    # impression | like | save | hide | share | broken   (v1-v3 also wrote view | skip)
    action = db.Column(db.String(12), nullable=False)
    value = db.Column(db.Float)  # engagement score for impressions (see ranking.engagement)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)


ERAS = ERAS  # re-export
