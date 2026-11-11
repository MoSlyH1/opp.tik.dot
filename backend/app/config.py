import os


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://opp:opp@localhost:5432/opptik")
    # Neon / Heroku style URLs -> SQLAlchemy + psycopg3 driver
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _list(name: str) -> list[str]:
    return [s.strip() for s in os.environ.get(name, "").split(",") if s.strip()]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
    DAILYMOTION = os.environ.get("DAILYMOTION", "1") == "1"   # keyless, on by default
    # Optional official social APIs (see app/providers/social.py). Empty = source off.
    META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
    IG_USER_ID = os.environ.get("IG_USER_ID", "")
    X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")
    REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

    CORS_ORIGINS = _list("CORS_ORIGINS") or ["http://localhost:5173", "http://localhost:8080"]
    ADMIN_EMAILS = {e.lower() for e in _list("ADMIN_EMAILS")}
    CRON_SECRET = os.environ.get("CRON_SECRET", "")
    # v12: address of the GitHub Pages site that publishes the small clips (the `clips` branch),
    # e.g. https://moslyh1.github.io/opp.tik.dot . Empty = every video plays from its original source.
    CLIPS_BASE = os.environ.get("CLIPS_BASE", "").strip().rstrip("/")
    # v12: optional Dailymotion Player ID (Dailymotion Studio -> Players), to pick your own player
    # settings. Empty = Dailymotion's default player, which works without an account.
    DM_PLAYER_ID = os.environ.get("DM_PLAYER_ID", "").strip()
    # v12: the "Sponsored" box on the loading card. All optional; empty = a house ad for the app.
    SPONSOR_TITLE = os.environ.get("SPONSOR_TITLE", "").strip()
    SPONSOR_TEXT = os.environ.get("SPONSOR_TEXT", "").strip()
    SPONSOR_URL = os.environ.get("SPONSOR_URL", "").strip()
    SPONSOR_IMAGE = os.environ.get("SPONSOR_IMAGE", "").strip()

    COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))

    SERVERLESS = bool(os.environ.get("VERCEL"))
    # Local-only shortcut for testing without Google. Never active on Vercel.
    DEV_LOGIN = os.environ.get("DEV_LOGIN", "0") == "1" and not SERVERLESS

    # Newest year that still counts as "nostalgic". 2009 = end of the 2000s.
    MAX_YEAR = int(os.environ.get("MAX_YEAR", "2009"))
