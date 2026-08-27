from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Read a conventional true/false value from the environment."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(url: str | None) -> str:
    """Return a SQLAlchemy URL, with a local SQLite development fallback."""
    if not url:
        return "sqlite:///homelab_dashboard.db"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def parse_allowed_emails(value: str) -> frozenset[str]:
    return frozenset(
        email.strip().lower() for email in value.split(",") if email.strip()
    )


class Config:
    APP_ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    DATABASE_URL_CONFIGURED = bool(os.getenv("DATABASE_URL"))
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.getenv("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {"pool_pre_ping": True}

    GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    ALLOW_INSECURE_DEV_AUTH = env_bool("ALLOW_INSECURE_DEV_AUTH", default=False)
    ALLOWED_GOOGLE_EMAILS = parse_allowed_emails(os.getenv("ALLOWED_GOOGLE_EMAILS", ""))

    SCHEDULER_ENABLED = env_bool("SCHEDULER_ENABLED", default=False)
    CHECK_TIMEOUT_SECONDS = float(os.getenv("CHECK_TIMEOUT_SECONDS", "10"))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=False)


def validate_config(app_config: dict[str, Any]) -> None:
    """Fail early when a non-test process is missing security-critical config."""
    if app_config.get("TESTING"):
        return
    if not app_config.get("SECRET_KEY"):
        raise RuntimeError(
            "FLASK_SECRET_KEY is required. Copy .env.example to .env and set it."
        )
    if app_config.get("APP_ENV") == "production":
        if app_config.get("ALLOW_INSECURE_DEV_AUTH"):
            raise RuntimeError(
                "Development authentication cannot be enabled in production."
            )
        required = (
            "DATABASE_URL_CONFIGURED",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "ALLOWED_GOOGLE_EMAILS",
        )
        missing = [name for name in required if not app_config.get(name)]
        if missing:
            raise RuntimeError(
                "Missing production configuration: " + ", ".join(missing)
            )
