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

    CORS_ORIGINS = _list("CORS_ORIGINS") or ["http://localhost:5173", "http://localhost:8080"]
    ADMIN_EMAILS = {e.lower() for e in _list("ADMIN_EMAILS")}
    CRON_SECRET = os.environ.get("CRON_SECRET", "")

    COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))

    SERVERLESS = bool(os.environ.get("VERCEL"))
    # Local-only shortcut for testing without Google. Never active on Vercel.
    DEV_LOGIN = os.environ.get("DEV_LOGIN", "0") == "1" and not SERVERLESS

    # Newest year that still counts as "nostalgic". 2009 = end of the 2000s.
    MAX_YEAR = int(os.environ.get("MAX_YEAR", "2009"))
