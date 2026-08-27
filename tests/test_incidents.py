from datetime import UTC, datetime, timedelta

from app.checks.persistence import persist_check_outcome
from app.checks.runners import CheckOutcome
from app.extensions import db
from app.models import Check, CheckType, Incident, Service, User


def create_service():
    user = User(email="incident-owner@example.com", name="Owner")
    service = Service(
        name="Incident target",
        target="https://example.com",
        check_type=CheckType.HTTP,
        interval_seconds=60,
        expected_status_code=200,
        creator=user,
    )
    db.session.add(service)
    db.session.commit()
    return service


def outcome(is_up, error=None):
    return CheckOutcome(
        is_up=is_up,
        response_time_ms=10.5,
        status_code=200 if is_up else None,
        error_message=error,
    )


def test_first_up_check_does_not_create_incident(app):
    with app.app_context():
        service = create_service()

        persist_check_outcome(service.id, outcome(True))

        assert db.session.query(Check).count() == 1
        assert db.session.query(Incident).count() == 0


def test_down_repetition_and_recovery_form_one_incident(app):
    with app.app_context():
        service = create_service()
        started = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

        persist_check_outcome(service.id, outcome(False, "offline"), checked_at=started)
        persist_check_outcome(
            service.id,
            outcome(False, "still offline"),
            checked_at=started + timedelta(seconds=30),
        )

        assert db.session.query(Check).count() == 2
        assert db.session.query(Incident).count() == 1
        incident = db.session.scalar(db.select(Incident))
        assert incident.resolved_at is None

        persist_check_outcome(
            service.id, outcome(True), checked_at=started + timedelta(seconds=75)
        )

        db.session.refresh(incident)
        assert db.session.query(Check).count() == 3
        assert db.session.query(Incident).count() == 1
        assert incident.resolved_at is not None
        assert incident.duration_seconds == 75


def test_up_to_down_opens_incident(app):
    with app.app_context():
        service = create_service()
        started = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
        persist_check_outcome(service.id, outcome(True), checked_at=started)

        persist_check_outcome(
            service.id, outcome(False), checked_at=started + timedelta(seconds=60)
        )

        incident = db.session.scalar(db.select(Incident))
        assert incident is not None
        comparable_started_at = incident.started_at.replace(tzinfo=UTC)
        assert comparable_started_at == started + timedelta(seconds=60)


def test_error_message_is_truncated(app):
    with app.app_context():
        service = create_service()

        check = persist_check_outcome(service.id, outcome(False, "x" * 700))

        assert len(check.error_message) == 500
