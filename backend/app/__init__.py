import logging

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import db


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if app.config["SERVERLESS"]:
        # Each serverless invocation is short-lived: let Neon's pooler do pooling.
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"poolclass": NullPool}
        if app.config["SECRET_KEY"] == "dev-only-change-me":
            raise RuntimeError("Set SECRET_KEY in production")
    elif not uri.startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280,
                                                   "pool_size": 5, "max_overflow": 10}

    db.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    from .auth import bp as auth_bp
    from .routes import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    @app.errorhandler(HTTPException)
    def http_error(e):
        body = {"error": e.description}
        if e.code == 404:
            body["path"] = request.path  # helps debugging routing problems
        return jsonify(body), e.code

    @app.errorhandler(Exception)
    def server_error(e):
        logging.exception("unhandled error")
        return jsonify(error="Something went wrong"), 500

    with app.app_context():
        from . import models  # noqa: F401
        _create_tables()

    return app


def _create_tables() -> None:
    """Create missing tables / columns without racing other cold starts.

    On serverless, several instances can boot at once and all run CREATE TABLE;
    Postgres then fails with "duplicate key ... pg_type". A transaction-level
    advisory lock makes the instances take turns.
    """
    try:
        with db.engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(8675309)"))
            db.metadata.create_all(conn)
            _migrate(conn)
    except Exception:
        # Don't take the whole API down (health, meta) if the DB is briefly unreachable.
        logging.exception("create_all failed")


# Columns added after v3. create_all() never alters existing tables, so add them here.
# Plain ADD COLUMN with a default works on Postgres and SQLite alike.
NEW_COLUMNS = {
    "items": [
        ("labels", "VARCHAR(400) NOT NULL DEFAULT ''"),
        ("lang", "VARCHAR(16)"),
        ("duration", "INTEGER"),
        ("media_url", "VARCHAR(800)"),
        ("impressions", "INTEGER NOT NULL DEFAULT 0"),
        ("engagement", "FLOAT NOT NULL DEFAULT 0"),
        ("broken", "INTEGER NOT NULL DEFAULT 0"),
        ("tax_v", "INTEGER NOT NULL DEFAULT 0"),
        ("media_info", "JSON"),
    ],
    "interactions": [("value", "FLOAT")],
}


def _migrate(conn) -> None:
    from sqlalchemy import inspect

    from .taxonomy import ERA_RANGES

    insp = inspect(conn)
    for table, cols in NEW_COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols:
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                logging.info("migrated: %s.%s", table, name)
    # v3 had one "classic" bucket for everything before 1990: split it by decade.
    if conn.execute(text("SELECT 1 FROM items WHERE era = 'classic' LIMIT 1")).first():
        for era, (y0, y1) in ERA_RANGES.items():
            conn.execute(text("UPDATE items SET era = :e WHERE era = 'classic' AND year BETWEEN :a AND :b"),
                         {"e": era, "a": y0, "b": y1})
        conn.execute(text("UPDATE items SET era = '80s' WHERE era = 'classic'"))
