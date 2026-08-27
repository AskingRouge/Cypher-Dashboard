import pytest

from app import create_app
from app.extensions import db, oauth
from app.models import User


@pytest.fixture()
def auth_app():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "auth-test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "WTF_CSRF_ENABLED": False,
            "SCHEDULER_ENABLED": False,
            "LOGIN_DISABLED": False,
            "APP_ENV": "development",
            "ALLOW_INSECURE_DEV_AUTH": True,
            "GOOGLE_OAUTH_CLIENT_ID": None,
            "GOOGLE_OAUTH_CLIENT_SECRET": None,
            "ALLOWED_GOOGLE_EMAILS": frozenset(),
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def auth_client(auth_app):
    return auth_app.test_client()


def test_unauthenticated_html_redirects_and_api_returns_401(auth_client):
    page = auth_client.get("/")
    api = auth_client.get("/api/services")

    assert page.status_code == 302
    assert "/auth/login" in page.location
    assert "next=/" in page.location
    assert api.status_code == 401
    assert api.json["error"] == "Authentication required"
    assert auth_client.get("/api/health").status_code == 200


def test_local_development_login_and_logout(auth_app, auth_client):
    login_page = auth_client.get("/auth/login")
    assert b"local development account" in login_page.data

    response = auth_client.post("/auth/local-login", data={"next": "/services/new"})

    assert response.status_code == 302
    assert response.location == "/services/new"
    assert auth_client.get("/").status_code == 200
    with auth_client.session_transaction() as session:
        assert session["email"] == "developer@localhost"
    with auth_app.app_context():
        assert db.session.query(User).count() == 1

    logout = auth_client.post("/auth/logout")
    assert logout.status_code == 302
    assert auth_client.get("/").status_code == 302


def test_local_login_rejects_external_next(auth_client):
    response = auth_client.post(
        "/auth/local-login", data={"next": "https://evil.example/steal"}
    )

    assert response.location == "/"


def test_disabled_google_login_returns_503(auth_client):
    assert auth_client.get("/auth/google").status_code == 503


def test_google_callback_upserts_user_and_stores_no_token(monkeypatch):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "google-test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "WTF_CSRF_ENABLED": False,
            "SCHEDULER_ENABLED": False,
            "LOGIN_DISABLED": False,
            "APP_ENV": "development",
            "ALLOW_INSECURE_DEV_AUTH": False,
            "GOOGLE_OAUTH_CLIENT_ID": "test-client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "test-client-secret",
            "ALLOWED_GOOGLE_EMAILS": frozenset({"person@example.com"}),
        }
    )
    with app.app_context():
        db.create_all()

    token = {
        "access_token": "must-not-enter-session",
        "userinfo": {
            "email": "Person@Example.com",
            "email_verified": True,
            "name": "Person One",
        },
    }
    monkeypatch.setattr(oauth.google, "authorize_access_token", lambda: token)
    client = app.test_client()

    first = client.get("/auth/callback")
    assert first.status_code == 302
    with client.session_transaction() as session:
        assert session["email"] == "person@example.com"
        assert "access_token" not in session
        assert "token" not in session

    token["userinfo"]["name"] = "Person Updated"
    second = client.get("/auth/callback")
    assert second.status_code == 302
    with app.app_context():
        users = db.session.scalars(db.select(User)).all()
        assert len(users) == 1
        assert users[0].name == "Person Updated"
        db.drop_all()
        db.session.remove()
        engine = db.engine
    engine.dispose()


def test_production_rejects_development_auth():
    with pytest.raises(RuntimeError, match="Development authentication"):
        create_app(
            {
                "TESTING": False,
                "APP_ENV": "production",
                "SECRET_KEY": "production-secret",
                "DATABASE_URL_CONFIGURED": True,
                "GOOGLE_OAUTH_CLIENT_ID": "client",
                "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
                "ALLOW_INSECURE_DEV_AUTH": True,
            }
        )
