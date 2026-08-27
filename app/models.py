from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


class CheckType(str, enum.Enum):
    HTTP = "http"
    PING = "ping"
    TCP_PORT = "tcp_port"


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    services: Mapped[list[Service]] = relationship(back_populates="creator")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Service(db.Model):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("interval_seconds >= 10", name="ck_services_interval_minimum"),
        CheckConstraint(
            "expected_status_code IS NULL OR "
            "(expected_status_code >= 100 AND expected_status_code <= 599)",
            name="ck_services_expected_status_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(2048))
    check_type: Mapped[CheckType] = mapped_column(
        Enum(
            CheckType,
            name="check_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    interval_seconds: Mapped[int] = mapped_column(Integer)
    expected_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    creator: Mapped[User] = relationship(back_populates="services")
    checks: Mapped[list[Check]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
        passive_deletes=False,
    )
    incidents: Mapped[list[Incident]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
        passive_deletes=False,
    )

    def __repr__(self) -> str:
        return f"<Service {self.name} ({self.check_type.value})>"


class Check(db.Model):
    __tablename__ = "checks"
    __table_args__ = (Index("ix_checks_service_timestamp", "service_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE")
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    is_up: Mapped[bool] = mapped_column(Boolean)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    service: Mapped[Service] = relationship(back_populates="checks")


class Incident(db.Model):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_service_started", "service_id", "started_at"),
        Index(
            "uq_incidents_one_open_per_service",
            "service_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
            sqlite_where=text("resolved_at IS NULL"),
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_incidents_duration_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    service: Mapped[Service] = relationship(back_populates="incidents")
