from datetime import datetime, timezone

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


ERAS = ["classic", "90s", "00s"]
ERA_LABELS = {"classic": "Before '90", "90s": "'90s", "00s": "2000s"}

CATEGORIES = ["movies", "music", "style", "tv", "ads", "tech", "games", "culture"]
CATEGORY_LABELS = {
    "movies": "Movies",
    "music": "Music videos",
    "style": "Style",
    "tv": "TV & cartoons",
    "ads": "Ads",
    "tech": "Tech",
    "games": "Games",
    "culture": "Culture",
}

SOURCES = ["tiktok", "youtube", "archive"]
SOURCE_LABELS = {"tiktok": "TikTok", "youtube": "YouTube", "archive": "Internet Archive"}


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
    category = db.Column(db.String(24), nullable=False, default="culture")
    tags = db.Column(db.JSON, nullable=False, default=list)
    score = db.Column(db.Float, nullable=False, default=0.5)
    likes_count = db.Column(db.Integer, nullable=False, default=0)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self, liked=False, saved=False):
        return {
            "id": self.id,
            "source": self.source,
            "source_label": SOURCE_LABELS.get(self.source, self.source),
            "external_id": self.external_id,
            "kind": self.kind,
            "url": self.url,
            "title": self.title,
            "author": self.author,
            "thumbnail": self.thumbnail,
            "era": self.era,
            "era_label": ERA_LABELS.get(self.era, self.era),
            "year": self.year,
            "category": self.category,
            "category_label": CATEGORY_LABELS.get(self.category, self.category),
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
    action = db.Column(db.String(12), nullable=False)  # view | skip | like | save | hide | share
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
