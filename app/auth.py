from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError

from app.decorators import login_required, safe_next_url
from app.development import get_or_create_development_user
from app.extensions import db, oauth
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def register_auth(app) -> None:
    if app.config.get("GOOGLE_OAUTH_CLIENT_ID") and app.config.get(
        "GOOGLE_OAUTH_CLIENT_SECRET"
    ):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )

    @app.before_request
    def load_logged_in_user() -> None:
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id is not None else None
        allowed = app.config["ALLOWED_GOOGLE_EMAILS"]
        if g.user is not None and allowed and g.user.email.lower() not in allowed:
            session.clear()
            g.user = None


@auth_bp.get("/login")
def login():
    if g.get("user") is not None:
        return redirect(url_for("dashboard.index"))
    next_url = safe_next_url(request.args.get("next"))
    return render_template(
        "login.html",
        next_url=next_url,
        google_enabled=_google_enabled(),
        development_login_enabled=current_app.config["ALLOW_INSECURE_DEV_AUTH"],
    )


@auth_bp.get("/google")
def google_login():
    if not _google_enabled():
        abort(503, "Google OAuth credentials are not configured.")
    session["post_login_next"] = safe_next_url(request.args.get("next"))
    redirect_uri = current_app.config.get("GOOGLE_OAUTH_REDIRECT_URI") or url_for(
        "auth.callback", _external=True
    )
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.get("/callback")
def callback():
    if not _google_enabled():
        abort(503, "Google OAuth credentials are not configured.")
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = oauth.google.userinfo(token=token)
    except Exception as exc:
        current_app.logger.warning(
            "Google OAuth callback failed (%s)", type(exc).__name__
        )
        abort(401, "Google authentication failed.")

    email = str(userinfo.get("email") or "").strip().lower()
    if not email or len(email) > 320 or userinfo.get("email_verified") is not True:
        abort(401, "Google did not provide a verified email address.")
    allowed = current_app.config["ALLOWED_GOOGLE_EMAILS"]
    if allowed and email not in allowed:
        session.clear()
        abort(403, "This Google account is not allowed to access this dashboard.")
    name = str(userinfo.get("name") or email.split("@", 1)[0]).strip()[:120]

    user = db.session.scalar(db.select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=name)
        db.session.add(user)
    else:
        user.name = name
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not persist Google user")
        abort(500)

    destination = safe_next_url(session.get("post_login_next"))
    _establish_session(user)
    return redirect(destination)


@auth_bp.post("/local-login")
def local_login():
    if not current_app.config["ALLOW_INSECURE_DEV_AUTH"]:
        abort(404)
    user = get_or_create_development_user()
    db.session.commit()
    destination = safe_next_url(request.form.get("next"))
    _establish_session(user)
    return redirect(destination)


@auth_bp.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def _establish_session(user: User) -> None:
    session.clear()
    session["user_id"] = user.id
    session["email"] = user.email
    session["name"] = user.name


def _google_enabled() -> bool:
    return bool(
        current_app.config.get("GOOGLE_OAUTH_CLIENT_ID")
        and current_app.config.get("GOOGLE_OAUTH_CLIENT_SECRET")
    )
