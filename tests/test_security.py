import pytest

from app import create_app
from app.decorators import safe_next_url
from app.extensions import db, oauth
from app.models import Service, User
from app.validation import normalize_service_input
from config import parse_allowed_emails, validate_config


@pytest.fixture()
def google_app(monkeypatch):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "WTF_CSRF_ENABLED": False,
            "SCHEDULER_ENABLED": False,
            "LOGIN_DISABLED": False,
            "ALLOW_INSECURE_DEV_AUTH": False,
            "GOOGLE_OAUTH_CLIENT_ID": "test-client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "test-client-secret",
            "ALLOWED_GOOGLE_EMAILS": frozenset({"owner@example.com"}),
        }
    )
    claims = {"email": "Owner@Example.com", "email_verified": True, "name": "Owner"}
    with app.app_context():
        db.create_all()
        monkeypatch.setattr(
            oauth.google, "authorize_access_token", lambda: {"userinfo": claims}
        )
        yield app, app.test_client(), claims
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.mark.parametrize("verification", [False, None, "true", 1])
def test_google_requires_explicitly_verified_email(google_app, verification):
    app, client, claims = google_app
    claims["email_verified"] = verification
    assert client.get("/auth/callback").status_code == 401
    assert db.session.query(User).count() == 0


def test_google_denies_non_allowlisted_account(google_app):
    app, client, claims = google_app
    claims["email"] = "stranger@example.com"
    assert client.get("/auth/callback").status_code == 403
    assert db.session.query(User).count() == 0
    assert client.get("/api/services").status_code == 401


def test_existing_session_is_revoked_when_removed_from_allowlist(google_app):
    app, client, claims = google_app
    assert client.get("/auth/callback").status_code == 302
    assert client.get("/api/services").status_code == 200
    app.config["ALLOWED_GOOGLE_EMAILS"] = frozenset({"another@example.com"})
    assert client.get("/api/services").status_code == 401
    with client.session_transaction() as session:
        assert "user_id" not in session


@pytest.mark.parametrize("api", [True, False])
def test_service_creation_uses_google_user_not_development_user(google_app, api):
    app, client, claims = google_app
    assert client.get("/auth/callback").status_code == 302
    payload = {
        "name": "Router",
        "check_type": "tcp_port",
        "target": "192.168.1.1:443",
        "interval_seconds": 30,
    }
    if api:
        response = client.post("/api/services", json=payload)
        assert response.status_code == 201
    else:
        response = client.post("/services/new", data=payload)
        assert response.status_code == 302
    service = db.session.scalar(db.select(Service))
    assert service is not None
    assert service.creator.email == "owner@example.com"
    assert db.session.query(User).count() == 1


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/",
        "//evil.example/",
        "/\\evil.example/",
        "/%5cevil.example/",
        "/%2fevil.example/",
        "/\n/evil.example/",
        "/%0d%0aLocation:evil.example",
        "//[invalid",
    ],
)
def test_next_url_rejects_browser_redirect_tricks(target):
    assert safe_next_url(target) == "/"


def test_next_url_preserves_local_path_and_query():
    assert safe_next_url("/services/new?source=login") == "/services/new?source=login"


def test_production_requires_allowlisted_administrators():
    with pytest.raises(RuntimeError, match="ALLOWED_GOOGLE_EMAILS"):
        validate_config(
            {
                "APP_ENV": "production",
                "SECRET_KEY": "test-production-secret",
                "DATABASE_URL_CONFIGURED": True,
                "GOOGLE_OAUTH_CLIENT_ID": "test-client",
                "GOOGLE_OAUTH_CLIENT_SECRET": "test-secret",
                "ALLOWED_GOOGLE_EMAILS": frozenset(),
            }
        )


def test_parse_allowed_emails_normalizes_case_and_whitespace():
    assert parse_allowed_emails("Owner@Example.com, , second@example.com ") == {
        "owner@example.com",
        "second@example.com",
    }


@pytest.mark.parametrize("interval", [10.5, float("inf"), float("nan"), True])
def test_interval_rejects_non_whole_or_non_finite_numbers(interval):
    normalized, errors = normalize_service_input(
        {
            "name": "Router",
            "check_type": "ping",
            "target": "192.168.1.1",
            "interval_seconds": interval,
        }
    )
    assert normalized is None
    assert "interval_seconds" in errors
