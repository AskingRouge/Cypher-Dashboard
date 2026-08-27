from datetime import UTC, datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.checks.scheduler import remove_service_job, schedule_service
from app.decorators import login_required, service_creator
from app.extensions import db
from app.models import Check, Incident, Service
from app.services import RANGES, build_service_summaries, iso_utc, summary_to_dict
from app.validation import ServiceInput, normalize_service_input

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/health")
def health():
    return jsonify({"data": {"status": "ok"}, "error": None})


@api_bp.get("/services")
@login_required
def list_services():
    services = db.session.scalars(db.select(Service).order_by(Service.name)).all()
    summaries = build_service_summaries(services)
    return jsonify(
        {"data": [summary_to_dict(item) for item in summaries], "error": None}
    )


@api_bp.get("/services/<int:service_id>/history")
@login_required
def service_history(service_id: int):
    db.get_or_404(Service, service_id)
    range_name = request.args.get("range", "24h")
    if range_name not in RANGES:
        return (
            jsonify(
                {
                    "data": None,
                    "error": {"range": "Range must be 24h, 7d, or 30d."},
                }
            ),
            400,
        )

    since = datetime.now(UTC) - RANGES[range_name]
    checks = db.session.scalars(
        db.select(Check)
        .where(Check.service_id == service_id, Check.timestamp >= since)
        .order_by(Check.timestamp.desc(), Check.id.desc())
        .limit(2000)
    ).all()
    points = [
        {
            "timestamp": iso_utc(check.timestamp),
            "is_up": check.is_up,
            "response_time_ms": check.response_time_ms,
            "status_code": check.status_code,
            "error_message": check.error_message,
        }
        for check in reversed(checks)
    ]
    return jsonify(
        {
            "data": {
                "service_id": service_id,
                "range": range_name,
                "points": points,
                "max_points": 2000,
            },
            "error": None,
        }
    )


@api_bp.get("/services/<int:service_id>/incidents")
@login_required
def service_incidents(service_id: int):
    db.get_or_404(Service, service_id)
    incidents = db.session.scalars(
        db.select(Incident)
        .where(Incident.service_id == service_id)
        .order_by(Incident.started_at.desc(), Incident.id.desc())
        .limit(100)
    ).all()
    return jsonify(
        {
            "data": [_serialize_incident(incident) for incident in incidents],
            "error": None,
        }
    )


@api_bp.post("/services")
@login_required
def create_service():
    data, errors = _validated_json()
    if errors:
        return _validation_error(errors)
    assert data is not None

    service = Service(creator=service_creator())
    _apply_input(service, data)
    try:
        db.session.add(service)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not create service")
        return _server_error()
    schedule_service(current_app._get_current_object(), service)
    return jsonify({"data": _serialize_service(service), "error": None}), 201


@api_bp.put("/services/<int:service_id>")
@login_required
def update_service(service_id: int):
    service = db.get_or_404(Service, service_id)
    data, errors = _validated_json()
    if errors:
        return _validation_error(errors)
    assert data is not None

    _apply_input(service, data)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not update service %s", service_id)
        return _server_error()
    schedule_service(current_app._get_current_object(), service)
    return jsonify({"data": _serialize_service(service), "error": None})


@api_bp.delete("/services/<int:service_id>")
@login_required
def delete_service(service_id: int):
    service = db.get_or_404(Service, service_id)
    try:
        db.session.delete(service)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not delete service %s", service_id)
        return _server_error()
    remove_service_job(service_id)
    return "", 204


def _validated_json() -> tuple[ServiceInput | None, dict[str, list[str]]]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, {"body": ["Request body must be a JSON object."]}
    return normalize_service_input(payload)


def _apply_input(service: Service, data: ServiceInput) -> None:
    service.name = data.name
    service.target = data.target
    service.check_type = data.check_type
    service.interval_seconds = data.interval_seconds
    service.expected_status_code = data.expected_status_code


def _serialize_service(service: Service) -> dict:
    return summary_to_dict(build_service_summaries([service])[0])


def _serialize_incident(incident: Incident) -> dict:
    now = datetime.now(UTC)
    started_at = incident.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    display_duration = incident.duration_seconds
    if display_duration is None:
        display_duration = max(0, int((now - started_at).total_seconds()))
    return {
        "id": incident.id,
        "started_at": iso_utc(incident.started_at),
        "resolved_at": iso_utc(incident.resolved_at) if incident.resolved_at else None,
        "duration_seconds": incident.duration_seconds,
        "display_duration_seconds": display_duration,
        "resolved": incident.resolved_at is not None,
    }


def _validation_error(errors: dict[str, list[str]]):
    return jsonify({"data": None, "error": {"fields": errors}}), 400


def _server_error():
    return jsonify({"data": None, "error": "Internal server error"}), 500
