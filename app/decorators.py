from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from urllib.parse import unquote, urlsplit

from flask import abort, current_app, g, jsonify, redirect, request, url_for


def login_required[ViewFunction: Callable](view: ViewFunction) -> ViewFunction:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_app.config.get("LOGIN_DISABLED") or g.get("user") is not None:
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"data": None, "error": "Authentication required"}), 401
        next_url = request.full_path.rstrip("?")
        return redirect(url_for("auth.login", next=next_url))

    return wrapped


def safe_next_url(value: str | None, default: str = "/") -> str:
    if not value:
        return default
    decoded = unquote(value)
    if "\\" in decoded or any(ord(char) < 32 or ord(char) == 127 for char in decoded):
        return default
    try:
        parsed = urlsplit(decoded)
    except ValueError:
        return default
    if (
        parsed.scheme
        or parsed.netloc
        or not value.startswith("/")
        or decoded.startswith("//")
    ):
        return default
    return value


def service_creator():
    """Attribute changes to the signed-in user, with a test-only fallback."""
    if g.get("user") is not None:
        return g.user
    if current_app.testing and current_app.config.get("LOGIN_DISABLED"):
        from app.development import get_or_create_development_user

        return get_or_create_development_user()
    abort(401)
