from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Check, CheckType, Incident, Service, User


def test_service_relations_and_cascade_delete(app):
    with app.app_context():
        user = User(email="owner@example.com", name="Owner")
        service = Service(
            name="Router",
            target="192.168.1.1",
            check_type=CheckType.PING,
            interval_seconds=60,
            created_by=1,
            creator=user,
        )
        service.checks.append(Check(is_up=True, response_time_ms=3.5))
        service.incidents.append(Incident(started_at=datetime.now(UTC)))
        db.session.add(service)
        db.session.commit()

        service_id = service.id
        db.session.delete(service)
        db.session.commit()

        assert db.session.get(Service, service_id) is None
        assert db.session.query(Check).count() == 0
        assert db.session.query(Incident).count() == 0


def test_user_email_is_unique(app):
    with app.app_context():
        db.session.add_all(
            [
                User(email="same@example.com", name="First"),
                User(email="same@example.com", name="Second"),
            ]
        )

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_service_interval_constraint(app):
    with app.app_context():
        user = User(email="owner@example.com", name="Owner")
        service = Service(
            name="Too frequent",
            target="https://example.com",
            check_type=CheckType.HTTP,
            interval_seconds=5,
            expected_status_code=200,
            creator=user,
        )
        db.session.add(service)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_only_one_open_incident_per_service(app):
    with app.app_context():
        user = User(email="owner@example.com", name="Owner")
        service = Service(
            name="Router",
            target="192.168.1.1",
            check_type=CheckType.PING,
            interval_seconds=60,
            creator=user,
        )
        now = datetime.now(UTC)
        service.incidents.extend([Incident(started_at=now), Incident(started_at=now)])
        db.session.add(service)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
