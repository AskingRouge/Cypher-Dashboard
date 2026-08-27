from flask import current_app

from app.extensions import db
from app.models import User

DEVELOPMENT_USER_EMAIL = "developer@localhost"


def get_or_create_development_user() -> User:
    """Temporary identity used only until Google OAuth is added in Phase 6."""
    if current_app.config["APP_ENV"] == "production":
        raise RuntimeError(
            "The temporary development identity is disabled in production."
        )

    user = db.session.scalar(
        db.select(User).where(User.email == DEVELOPMENT_USER_EMAIL)
    )
    if user is None:
        user = User(email=DEVELOPMENT_USER_EMAIL, name="Local Developer")
        db.session.add(user)
        db.session.flush()
    return user
