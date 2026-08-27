from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db
from app.models import Check, CheckType, Incident, Service, User
from app.services import build_service_summaries, summary_to_dict


def create_summary_service(*, name="Summary", interval=60):
    user = User(email=f"{name.lower()}@example.com", name="Owner")
    service = Service(
        name=name,
        target="https://example.com",
        check_type=CheckType.HTTP,
        interval_seconds=interval,
        expected_status_code=200,
        creator=user,
    )
    db.session.add(service)
    db.session.commit()
    return service


def test_unknown_summary_has_no_claimed_uptime(app):
    with app.app_context():
        service = create_summary_service()

        summary = build_service_summaries([service])[0]
        serialized = summary_to_dict(summary)

        assert summary.status == "unknown"
        assert summary.latest is None
        assert summary.uptime == {"24h": None, "7d": None, "30d": None}
        assert serialized["last_checked_at"] is None


def test_summary_uses_latest_check_and_range_aggregates(app):
    now = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)
    with app.app_context():
        service = create_summary_service()
        service.checks.extend(
            [
                Check(timestamp=now - timedelta(days=2), is_up=True),
                Check(timestamp=now - timedelta(hours=1), is_up=False),
                Check(
                    timestamp=now - timedelta(seconds=30),
                    is_up=True,
                    response_time_ms=12.25,
                ),
            ]
        )
        db.session.commit()

        summary = build_service_summaries([service], now=now)[0]

        assert summary.status == "up"
        assert summary.latest.response_time_ms == 12.25
        assert summary.uptime["24h"] == 50
        assert summary.uptime["7d"] == pytest.approx(66.666, rel=1e-3)
        assert summary.uptime["30d"] == pytest.approx(66.666, rel=1e-3)


def test_old_latest_check_is_stale(app):
    now = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)
    with app.app_context():
        service = create_summary_service(name="Stale", interval=10)
        service.checks.append(Check(timestamp=now - timedelta(minutes=2), is_up=False))
        db.session.commit()

        summary = build_service_summaries([service], now=now)[0]

        assert summary.status == "stale"


def test_down_summary_reports_open_incident(app):
    now = datetime(2026, 8, 26, 15, 0, tzinfo=UTC)
    with app.app_context():
        service = create_summary_service(name="Down")
        service.checks.append(Check(timestamp=now, is_up=False))
        service.incidents.append(Incident(started_at=now))
        db.session.commit()

        summary = build_service_summaries([service], now=now)[0]

        assert summary.status == "down"
        assert summary.has_open_incident is True


def test_dashboard_and_api_render_live_summary(app, client):
    with app.app_context():
        service = create_summary_service(name="Live")
        service.checks.append(Check(is_up=True, response_time_ms=8.75))
        db.session.commit()

    page = client.get("/")
    api = client.get("/api/services")

    assert page.status_code == 200
    assert b"status-up" in page.data
    assert b"8.8 ms" in page.data
    assert api.json["data"][0]["status"] == "up"
    assert api.json["data"][0]["uptime"]["24h"] == 100
