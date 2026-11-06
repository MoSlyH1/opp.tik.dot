import logging

from flask import Flask, jsonify
from flask_cors import CORS
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
        return jsonify(error=e.description), e.code

    @app.errorhandler(Exception)
    def server_error(e):
        logging.exception("unhandled error")
        return jsonify(error="Something went wrong"), 500

    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()

    return app
