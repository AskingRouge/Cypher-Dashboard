from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func

from app.extensions import db
from app.models import Check, Incident, Service

RANGES = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@dataclass(frozen=True, slots=True)
class LatestCheck:
    timestamp: datetime
    is_up: bool
    response_time_ms: float | None


@dataclass(frozen=True, slots=True)
class ServiceSummary:
    service: Service
    status: str
    latest: LatestCheck | None
    uptime: dict[str, float | None]
    has_open_incident: bool


def build_service_summaries(
    services: Iterable[Service], *, now: datetime | None = None
) -> list[ServiceSummary]:
    service_list = list(services)
    if not service_list:
        return []

    current_time = _as_utc(now or datetime.now(UTC))
    service_ids = [service.id for service in service_list]
    latest_by_service = _latest_checks(service_ids)
    uptime_by_range = {
        range_name: _uptime_since(service_ids, current_time - duration)
        for range_name, duration in RANGES.items()
    }
    open_incidents = set(
        db.session.scalars(
            db.select(Incident.service_id).where(
                Incident.service_id.in_(service_ids),
                Incident.resolved_at.is_(None),
            )
        )
    )

    return [
        ServiceSummary(
            service=service,
            status=_current_status(
                service, latest_by_service.get(service.id), current_time
            ),
            latest=latest_by_service.get(service.id),
            uptime={
                range_name: values.get(service.id)
                for range_name, values in uptime_by_range.items()
            },
            has_open_incident=service.id in open_incidents,
        )
        for service in service_list
    ]


def summary_to_dict(summary: ServiceSummary) -> dict:
    service = summary.service
    return {
        "id": service.id,
        "name": service.name,
        "target": service.target,
        "check_type": service.check_type.value,
        "interval_seconds": service.interval_seconds,
        "expected_status_code": service.expected_status_code,
        "created_at": iso_utc(service.created_at),
        "status": summary.status,
        "response_time_ms": (
            summary.latest.response_time_ms if summary.latest is not None else None
        ),
        "last_checked_at": (
            iso_utc(summary.latest.timestamp) if summary.latest is not None else None
        ),
        "uptime": summary.uptime,
        "has_open_incident": summary.has_open_incident,
    }


def _latest_checks(service_ids: list[int]) -> dict[int, LatestCheck]:
    ranked = (
        db.select(
            Check.service_id.label("service_id"),
            Check.timestamp.label("timestamp"),
            Check.is_up.label("is_up"),
            Check.response_time_ms.label("response_time_ms"),
            func.row_number()
            .over(
                partition_by=Check.service_id,
                order_by=(Check.timestamp.desc(), Check.id.desc()),
            )
            .label("rank"),
        )
        .where(Check.service_id.in_(service_ids))
        .subquery()
    )
    rows = db.session.execute(db.select(ranked).where(ranked.c.rank == 1)).mappings()
    return {
        row["service_id"]: LatestCheck(
            timestamp=row["timestamp"],
            is_up=row["is_up"],
            response_time_ms=row["response_time_ms"],
        )
        for row in rows
    }


def _uptime_since(service_ids: list[int], since: datetime) -> dict[int, float]:
    rows = db.session.execute(
        db.select(
            Check.service_id,
            func.count(Check.id).label("total"),
            func.sum(case((Check.is_up.is_(True), 1), else_=0)).label("up_count"),
        )
        .where(Check.service_id.in_(service_ids), Check.timestamp >= since)
        .group_by(Check.service_id)
    )
    return {
        service_id: (float(up_count) / total) * 100
        for service_id, total, up_count in rows
        if total
    }


def _current_status(service: Service, latest: LatestCheck | None, now: datetime) -> str:
    if latest is None:
        return "unknown"
    stale_after = max(
        timedelta(seconds=service.interval_seconds * 2),
        timedelta(seconds=service.interval_seconds + 30),
    )
    if now - _as_utc(latest.timestamp) > stale_after:
        return "stale"
    return "up" if latest.is_up else "down"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")
