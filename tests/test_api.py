from datetime import UTC, datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import Check, Incident, Service


def api_payload(**overrides):
    payload = {
        "name": "Example API",
        "target": "https://example.com",
        "check_type": "http",
        "interval_seconds": 60,
        "expected_status_code": 200,
    }
    payload.update(overrides)
    return payload


def test_api_service_crud(app, client):
    assert client.get("/api/services").json["data"] == []

    create_response = client.post("/api/services", json=api_payload())
    assert create_response.status_code == 201
    service_id = create_response.json["data"]["id"]
    assert create_response.json["data"]["status"] == "unknown"

    list_response = client.get("/api/services")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json["data"]] == [service_id]

    update_response = client.put(
        f"/api/services/{service_id}",
        json=api_payload(
            name="DNS",
            target="192.168.1.53:53",
            check_type="tcp_port",
            interval_seconds=30,
        ),
    )
    assert update_response.status_code == 200
    assert update_response.json["data"]["name"] == "DNS"
    assert update_response.json["data"]["expected_status_code"] is None

    delete_response = client.delete(f"/api/services/{service_id}")
    assert delete_response.status_code == 204
    with app.app_context():
        assert db.session.get(Service, service_id) is None


def test_api_validation_errors_are_structured(client):
    response = client.post(
        "/api/services",
        json=api_payload(target="ftp://example.com", interval_seconds=1),
    )

    assert response.status_code == 400
    fields = response.json["error"]["fields"]
    assert "target" in fields
    assert "interval_seconds" in fields


def test_api_requires_json_object(client):
    response = client.post("/api/services", data="not json", content_type="text/plain")

    assert response.status_code == 400
    assert "body" in response.json["error"]["fields"]


def test_api_missing_service_returns_json_404(client):
    response = client.delete("/api/services/999")

    assert response.status_code == 404
    assert response.json == {"data": None, "error": "Not found"}


def test_mutating_api_rejects_missing_csrf_token():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "WTF_CSRF_ENABLED": True,
            "SCHEDULER_ENABLED": False,
            "LOGIN_DISABLED": True,
        }
    )
    client = app.test_client()

    response = client.post("/api/services", json=api_payload())

    assert response.status_code == 400
    assert "csrf" in response.json["error"]
    with app.app_context():
        db.engine.dispose()


def test_history_endpoint_filters_range_and_sorts(app, client):
    create_response = client.post("/api/services", json=api_payload())
    service_id = create_response.json["data"]["id"]
    now = datetime.now(UTC)
    with app.app_context():
        service = db.session.get(Service, service_id)
        service.checks.extend(
            [
                Check(timestamp=now - timedelta(days=2), is_up=True),
                Check(
                    timestamp=now - timedelta(minutes=10),
                    is_up=False,
                    error_message="offline",
                ),
                Check(
                    timestamp=now - timedelta(minutes=5),
                    is_up=True,
                    response_time_ms=9.5,
                    status_code=200,
                ),
            ]
        )
        db.session.commit()

    response = client.get(f"/api/services/{service_id}/history?range=24h")

    assert response.status_code == 200
    points = response.json["data"]["points"]
    assert len(points) == 2
    assert [point["is_up"] for point in points] == [False, True]
    assert points[0]["timestamp"] < points[1]["timestamp"]

    seven_days = client.get(f"/api/services/{service_id}/history?range=7d")
    assert len(seven_days.json["data"]["points"]) == 3


def test_history_endpoint_rejects_invalid_range(client):
    created = client.post("/api/services", json=api_payload())
    service_id = created.json["data"]["id"]

    response = client.get(f"/api/services/{service_id}/history?range=forever")

    assert response.status_code == 400
    assert "range" in response.json["error"]


def test_incident_endpoint_returns_ongoing_and_resolved(app, client):
    created = client.post("/api/services", json=api_payload())
    service_id = created.json["data"]["id"]
    now = datetime.now(UTC)
    with app.app_context():
        service = db.session.get(Service, service_id)
        service.incidents.extend(
            [
                Incident(
                    started_at=now - timedelta(minutes=10),
                    resolved_at=now - timedelta(minutes=5),
                    duration_seconds=300,
                ),
                Incident(started_at=now - timedelta(seconds=30)),
            ]
        )
        db.session.commit()

    response = client.get(f"/api/services/{service_id}/incidents")

    assert response.status_code == 200
    incidents = response.json["data"]
    assert incidents[0]["resolved"] is False
    assert incidents[0]["duration_seconds"] is None
    assert incidents[0]["display_duration_seconds"] >= 29
    assert incidents[1]["resolved"] is True
    assert incidents[1]["duration_seconds"] == 300


def test_history_and_incident_missing_service_return_json_404(client):
    assert client.get("/api/services/999/history").status_code == 404
    assert client.get("/api/services/999/incidents").status_code == 404
