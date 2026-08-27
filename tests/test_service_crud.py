from app.extensions import db
from app.models import CheckType, Service, User


def form_payload(**overrides):
    payload = {
        "name": "Example site",
        "target": "https://example.com/health",
        "check_type": "http",
        "interval_seconds": "60",
        "expected_status_code": "200",
    }
    payload.update(overrides)
    return payload


def test_dashboard_has_service_empty_state(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"No services yet" in response.data
    assert b"Add your first service" in response.data


def test_html_create_edit_and_delete_service(app, client):
    create_response = client.post(
        "/services/new", data=form_payload(), follow_redirects=True
    )

    assert create_response.status_code == 200
    assert b"Added Example site" in create_response.data
    with app.app_context():
        service = db.session.scalar(db.select(Service))
        assert service is not None
        service_id = service.id
        assert service.creator.email == "developer@localhost"

    edit_response = client.post(
        f"/services/{service_id}/edit",
        data=form_payload(
            name="Router SSH",
            target="router.local:22",
            check_type="tcp_port",
            interval_seconds="30",
        ),
        follow_redirects=True,
    )

    assert edit_response.status_code == 200
    assert b"Updated Router SSH" in edit_response.data
    with app.app_context():
        service = db.session.get(Service, service_id)
        assert service is not None
        assert service.check_type is CheckType.TCP_PORT
        assert service.expected_status_code is None

    delete_response = client.post(
        f"/services/{service_id}/delete", follow_redirects=True
    )

    assert delete_response.status_code == 200
    assert b"Deleted Router SSH" in delete_response.data
    with app.app_context():
        assert db.session.get(Service, service_id) is None
        assert db.session.query(User).count() == 1


def test_html_form_displays_shared_target_error(client):
    response = client.post(
        "/services/new",
        data=form_payload(target="not-a-url"),
    )

    assert response.status_code == 200
    assert b"HTTP targets must use http:// or https://" in response.data


def test_missing_service_returns_404(client):
    assert client.get("/services/999").status_code == 404
    assert client.post("/services/999/delete").status_code == 404


def test_detail_page_contains_chart_and_incident_ui(app, client):
    created = client.post(
        "/api/services",
        json={
            "name": "Chart target",
            "target": "https://example.com",
            "check_type": "http",
            "interval_seconds": 60,
            "expected_status_code": 200,
        },
    )
    service_id = created.json["data"]["id"]

    response = client.get(f"/services/{service_id}")

    assert response.status_code == 200
    assert b"response-time-chart" in response.data
    assert b"Incident history" in response.data
    assert b'data-history-range="24h"' in response.data
    assert b"chart.js@4.5.0" in response.data
