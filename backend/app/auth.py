from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Blueprint, current_app, g, jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .extensions import db
from .models import User, utcnow

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
COOKIE = "opp_session"


def _issue(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "iat": now,
               "exp": now + timedelta(days=current_app.config["SESSION_DAYS"])}
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def current_user() -> User | None:
    token = request.cookies.get(COOKIE)
    auth = request.headers.get("Authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        return None
    try:
        data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return db.session.get(User, int(data["sub"]))


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user = current_user()
        if not user:
            return jsonify(error="Sign in required"), 401
        g.user = user
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*a, **kw):
        if g.user.email.lower() not in current_app.config["ADMIN_EMAILS"]:
            return jsonify(error="Admins only"), 403
        return fn(*a, **kw)
    return wrapper


def _session_response(user: User):
    resp = jsonify(user=user.to_dict(current_app.config["ADMIN_EMAILS"]))
    resp.set_cookie(COOKIE, _issue(user), httponly=True, samesite="Lax",
                    secure=current_app.config["COOKIE_SECURE"],
                    max_age=current_app.config["SESSION_DAYS"] * 86400, path="/")
    return resp


def _upsert_user(sub, email, name, avatar) -> User:
    user = User.query.filter_by(google_sub=sub).first()
    if not user:
        user = User(google_sub=sub, email=email, prefs={})
        db.session.add(user)
    user.email, user.name, user.avatar, user.last_seen_at = email, name, avatar, utcnow()
    db.session.commit()
    return user


@bp.post("/google")
def google_login():
    credential = (request.get_json(silent=True) or {}).get("credential")
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    if not credential or not client_id:
        return jsonify(error="Missing Google credential or server client id"), 400
    try:
        info = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    except ValueError:
        return jsonify(error="Invalid Google sign-in"), 401
    if not info.get("email_verified"):
        return jsonify(error="Google email not verified"), 401
    user = _upsert_user(info["sub"], info["email"], info.get("name"), info.get("picture"))
    return _session_response(user)


@bp.post("/dev")
def dev_login():
    """Local testing only (DEV_LOGIN=1, never on Vercel)."""
    if not current_app.config["DEV_LOGIN"]:
        return jsonify(error="Not found"), 404
    email = (request.get_json(silent=True) or {}).get("email", "dev@local.test")
    return _session_response(_upsert_user(f"dev:{email}", email, "Dev User", None))


@bp.get("/me")
def me():
    user = current_user()
    if not user:
        return jsonify(user=None)
    return jsonify(user=user.to_dict(current_app.config["ADMIN_EMAILS"]))


@bp.post("/logout")
def logout():
    resp = jsonify(ok=True)
    resp.delete_cookie(COOKIE, path="/")
    return resp
