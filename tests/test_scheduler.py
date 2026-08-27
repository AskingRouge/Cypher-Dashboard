from app.checks import scheduler as scheduler_module
from app.checks.runners import CheckOutcome
from app.extensions import db
from app.models import CheckType, Service, User


def test_execute_service_check_dispatches_and_persists(app, monkeypatch):
    with app.app_context():
        user = User(email="scheduler@example.com", name="Scheduler")
        service = Service(
            name="Scheduled",
            target="https://example.com",
            check_type=CheckType.HTTP,
            interval_seconds=60,
            expected_status_code=204,
            creator=user,
        )
        db.session.add(service)
        db.session.commit()
        service_id = service.id

    captured = {}
    expected_outcome = CheckOutcome(True, 12.5, status_code=204)

    def fake_run_check(**kwargs):
        captured["run"] = kwargs
        return expected_outcome

    def fake_persist(service_id, result):
        captured["persist"] = (service_id, result)

    monkeypatch.setattr(scheduler_module, "run_check", fake_run_check)
    monkeypatch.setattr(scheduler_module, "persist_check_outcome", fake_persist)

    scheduler_module.execute_service_check(app, service_id)

    assert captured["run"]["target"] == "https://example.com"
    assert captured["run"]["expected_status_code"] == 204
    assert captured["run"]["timeout_seconds"] == 10
    assert captured["persist"] == (service_id, expected_outcome)


def test_missing_service_check_is_ignored(app, monkeypatch):
    removed = []
    monkeypatch.setattr(scheduler_module, "remove_service_job", removed.append)

    scheduler_module.execute_service_check(app, 999)

    assert removed == [999]


def test_service_job_id_is_stable():
    assert scheduler_module.service_job_id(42) == "service-check-42"
