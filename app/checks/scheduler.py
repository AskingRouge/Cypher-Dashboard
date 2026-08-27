from __future__ import annotations

import atexit
import threading
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from sqlalchemy.exc import SQLAlchemyError

from app.checks.persistence import persist_check_outcome
from app.checks.runners import run_check
from app.extensions import db
from app.models import Service

scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
_scheduler_lock = threading.Lock()
_shutdown_registered = False


def register_scheduler_startup(app: Flask) -> None:
    """Start once when this process receives its first HTTP request."""
    if not app.config["SCHEDULER_ENABLED"] or app.config.get("TESTING"):
        return

    @app.before_request
    def ensure_scheduler_started() -> None:
        start_scheduler(app)


def start_scheduler(app: Flask) -> None:
    global _shutdown_registered
    if scheduler.running:
        return

    with _scheduler_lock:
        if scheduler.running:
            return
        with app.app_context():
            services = db.session.scalars(db.select(Service)).all()
            for service in services:
                _add_or_replace_job(app, service.id, service.interval_seconds)
        scheduler.start()
        app.logger.info("Health-check scheduler started with %d jobs", len(services))
        if not _shutdown_registered:
            atexit.register(shutdown_scheduler)
            _shutdown_registered = True


def schedule_service(app: Flask, service: Service) -> None:
    if scheduler.running:
        _add_or_replace_job(app, service.id, service.interval_seconds)


def remove_service_job(service_id: int) -> None:
    job = scheduler.get_job(service_job_id(service_id))
    if job is not None:
        scheduler.remove_job(job.id)


def service_job_id(service_id: int) -> str:
    return f"service-check-{service_id}"


def execute_service_check(app: Flask, service_id: int) -> None:
    with app.app_context():
        service = db.session.get(Service, service_id)
        if service is None:
            remove_service_job(service_id)
            return

        check_type = service.check_type
        target = service.target
        expected_status = service.expected_status_code
        interval = service.interval_seconds
        configured_timeout = float(app.config["CHECK_TIMEOUT_SECONDS"])
        timeout = min(configured_timeout, max(2.0, interval / 2))
        db.session.remove()

        try:
            outcome = run_check(
                check_type=check_type,
                target=target,
                expected_status_code=expected_status,
                timeout_seconds=timeout,
            )
            persist_check_outcome(service_id, outcome)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Could not persist check for service %s", service_id)
        except Exception:
            db.session.rollback()
            app.logger.exception("Unexpected check failure for service %s", service_id)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _add_or_replace_job(app: Flask, service_id: int, interval_seconds: int) -> None:
    scheduler.add_job(
        execute_service_check,
        trigger="interval",
        seconds=interval_seconds,
        id=service_job_id(service_id),
        args=(app, service_id),
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30,
        next_run_time=datetime.now(UTC),
    )
