"""Administrative endpoints; the password and session signing key stay server-side."""

import hashlib
import hmac
import ipaddress
import logging
import secrets
import sqlite3
import time
from functools import wraps

from flask import Blueprint, Response, current_app, request, session
from werkzeug.security import check_password_hash

from .http import error_response, json_response
from .rejected import normalize_word

logger = logging.getLogger(__name__)


def login_client_key():
    """Trust the overwritten Nginx header only from explicitly configured peers."""
    try:
        peer = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        peer = None
    client = peer
    trusted = current_app.config.get("TRUSTED_PROXY_CIDRS", ())
    if peer is not None and any(peer in network for network in trusted):
        try:
            client = ipaddress.ip_address(request.headers.get("X-Real-IP", ""))
        except ValueError:
            client = peer
    identity = str(client) if client is not None else "unknown"
    return hmac.new(current_app.secret_key.encode(), identity.encode(), hashlib.sha256).hexdigest()


def create_admin_routes(store):
    bp = Blueprint("admin", __name__, url_prefix="/api/admin")

    def authorized():
        password_hash = current_app.config["ADMIN_PASSWORD_HASH"]
        fingerprint = hmac.new(
            current_app.secret_key.encode(), password_hash.encode(), hashlib.sha256
        ).hexdigest()
        return bool(
            password_hash
            and session.get("admin") == fingerprint
            and store.has_session(session.get("session_id", ""), time.time())
        )

    def guarded(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not authorized():
                return error_response("unauthorized", "Требуется вход администратора", 401)
            if request.method == "POST" and not csrf_ok():
                return error_response("csrf_failed", "Ошибка проверки запроса", 403)
            return fn(*args, **kwargs)

        return wrapper

    def csrf_ok():
        token = session.get("csrf", "")
        return bool(token and hmac.compare_digest(token, request.headers.get("X-CSRF-Token", "")))

    @bp.errorhandler(sqlite3.Error)
    def database_error(_exc):
        logger.exception("administrative database operation failed")
        return error_response("database_error", "Ошибка базы исключённых слов", 503)

    @bp.get("/session")
    def get_session():
        if not session.get("csrf"):
            session["csrf"] = secrets.token_urlsafe(32)
        response = json_response({"authenticated": authorized(), "csrf_token": session["csrf"]})
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/login")
    def login():
        if not csrf_ok():
            return error_response("csrf_failed", "Ошибка проверки запроса", 403)
        data = request.get_json(silent=True)
        password = data.get("password") if isinstance(data, dict) else None
        if not isinstance(password, str) or len(password) > 1024:
            return error_response("bad_request", "Введите пароль", 400)
        password_hash = current_app.config["ADMIN_PASSWORD_HASH"]
        if not password_hash:
            return error_response("unavailable", "Административный доступ не настроен", 503)
        client_key = login_client_key()
        if not store.login_attempt(client_key, time.time()):
            return error_response("rate_limited", "Слишком много попыток. Попробуйте позже", 429)
        if not check_password_hash(password_hash, password):
            return error_response("invalid_credentials", "Неверный пароль", 401)
        store.clear_attempts(client_key)
        session.clear()
        session.permanent = True
        session["admin"] = hmac.new(
            current_app.secret_key.encode(), password_hash.encode(), hashlib.sha256
        ).hexdigest()
        session["session_id"] = secrets.token_urlsafe(32)
        store.create_session(session["session_id"], time.time() + 90 * 86400)
        session["csrf"] = secrets.token_urlsafe(32)
        return json_response({"authenticated": True, "csrf_token": session["csrf"]})

    @bp.post("/logout")
    @guarded
    def logout():
        store.delete_session(session.get("session_id", ""))
        session.clear()
        session["csrf"] = secrets.token_urlsafe(32)
        return json_response({"authenticated": False, "csrf_token": session["csrf"]})

    @bp.get("/rejected")
    @guarded
    def rejected():
        search = request.args.get("search", "").strip().lower()
        if len(search) > 25:
            return error_response("bad_request", "Слишком длинный запрос", 400)
        try:
            page = max(1, min(int(request.args.get("page", 1)), 1000000))
        except ValueError:
            return error_response("bad_request", "Некорректная страница", 400)
        total, count, rows = store.list_words(search, 50, (page - 1) * 50)
        return json_response(
            {
                "total": total,
                "matched": count,
                "page": page,
                "words": [{"word": w, "rejected_at": d} for w, d in rows],
            }
        )

    def change(restore=False):
        data = request.get_json(silent=True)
        try:
            word = normalize_word(data.get("word") if isinstance(data, dict) else None)
        except ValueError as exc:
            return error_response("bad_request", str(exc), 400)
        if restore:
            store.restore(word)
            return json_response({"word": word})
        return json_response({"word": word, "created": store.reject(word)})

    @bp.post("/rejected")
    @guarded
    def reject():
        return change()

    @bp.post("/rejected/restore")
    @guarded
    def restore():
        return change(True)

    @bp.get("/rejected/export")
    @guarded
    def export():
        words = sorted(store.snapshot())
        response = Response(
            "".join(word + "\n" for word in words), content_type="text/plain; charset=utf-8"
        )
        response.headers["Content-Disposition"] = 'attachment; filename="rejected-words.txt"'
        response.headers["Cache-Control"] = "no-store"
        return response

    return bp
