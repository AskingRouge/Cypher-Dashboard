from __future__ import annotations

from datetime import UTC, datetime

from app.checks.runners import CheckOutcome
from app.extensions import db
from app.models import Check, Incident


def persist_check_outcome(
    service_id: int,
    outcome: CheckOutcome,
    *,
    checked_at: datetime | None = None,
) -> Check:
    """Append a result and apply its incident transition in one transaction."""
    timestamp = _as_utc(checked_at or datetime.now(UTC))
    previous = db.session.scalar(
        db.select(Check)
        .where(Check.service_id == service_id)
        .order_by(Check.timestamp.desc(), Check.id.desc())
        .limit(1)
    )

    check = Check(
        service_id=service_id,
        timestamp=timestamp,
        is_up=outcome.is_up,
        response_time_ms=outcome.response_time_ms,
        status_code=outcome.status_code,
        error_message=_truncate_error(outcome.error_message),
    )
    db.session.add(check)

    if outcome.is_up:
        if previous is not None and not previous.is_up:
            _resolve_open_incident(service_id, timestamp)
    elif previous is None or previous.is_up:
        db.session.add(Incident(service_id=service_id, started_at=timestamp))

    db.session.commit()
    return check


def _resolve_open_incident(service_id: int, resolved_at: datetime) -> None:
    incident = db.session.scalar(
        db.select(Incident)
        .where(
            Incident.service_id == service_id,
            Incident.resolved_at.is_(None),
        )
        .order_by(Incident.started_at.desc())
        .limit(1)
    )
    if incident is None:
        return
    incident.resolved_at = resolved_at
    incident.duration_seconds = max(
        0, int((resolved_at - _as_utc(incident.started_at)).total_seconds())
    )


def _truncate_error(message: str | None) -> str | None:
    return message[:500] if message else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
