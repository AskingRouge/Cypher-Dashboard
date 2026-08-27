from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.models import CheckType

HOST_LABEL_PATTERN = re.compile(r"^(?!-)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
DENIED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.google.internal.",
}


@dataclass(frozen=True, slots=True)
class ServiceInput:
    name: str
    target: str
    check_type: CheckType
    interval_seconds: int
    expected_status_code: int | None


def normalize_service_input(
    values: Mapping[str, Any],
) -> tuple[ServiceInput | None, dict[str, list[str]]]:
    """Validate and normalize service data shared by forms and JSON routes."""
    errors: dict[str, list[str]] = {}

    name = str(values.get("name") or "").strip()
    if not name:
        _add_error(errors, "name", "Name is required.")
    elif len(name) > 100:
        _add_error(errors, "name", "Name must be 100 characters or fewer.")

    check_type = _parse_check_type(values.get("check_type"), errors)
    interval = _parse_integer(
        values.get("interval_seconds"),
        field="interval_seconds",
        errors=errors,
        minimum=10,
        maximum=86_400,
    )

    target = str(values.get("target") or "").strip()
    normalized_target: str | None = None
    if not target:
        _add_error(errors, "target", "Target is required.")
    elif len(target) > 2048:
        _add_error(errors, "target", "Target must be 2048 characters or fewer.")
    elif check_type is not None:
        normalized_target = _normalize_target(target, check_type, errors)

    expected_status: int | None = None
    if check_type is CheckType.HTTP:
        raw_status = values.get("expected_status_code")
        if raw_status in (None, ""):
            expected_status = 200
        else:
            expected_status = _parse_integer(
                raw_status,
                field="expected_status_code",
                errors=errors,
                minimum=100,
                maximum=599,
            )

    if errors or check_type is None or interval is None or normalized_target is None:
        return None, errors

    return (
        ServiceInput(
            name=name,
            target=normalized_target,
            check_type=check_type,
            interval_seconds=interval,
            expected_status_code=expected_status,
        ),
        {},
    )


def _parse_check_type(value: Any, errors: dict[str, list[str]]) -> CheckType | None:
    if isinstance(value, CheckType):
        return value
    try:
        return CheckType(str(value))
    except (TypeError, ValueError):
        _add_error(
            errors,
            "check_type",
            "Check type must be http, ping, or tcp_port.",
        )
        return None


def _parse_integer(
    value: Any,
    *,
    field: str,
    errors: dict[str, list[str]],
    minimum: int,
    maximum: int,
) -> int | None:
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        parsed = None
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = None

    if parsed is None:
        _add_error(errors, field, "Must be a whole number.")
    elif not minimum <= parsed <= maximum:
        _add_error(errors, field, f"Must be between {minimum} and {maximum}.")
    else:
        return parsed
    return None


def _normalize_target(
    target: str, check_type: CheckType, errors: dict[str, list[str]]
) -> str | None:
    if check_type is CheckType.HTTP:
        return _normalize_http_target(target, errors)
    if check_type is CheckType.TCP_PORT:
        return _normalize_tcp_target(target, errors)
    return _normalize_ping_target(target, errors)


def _normalize_http_target(target: str, errors: dict[str, list[str]]) -> str | None:
    try:
        parsed = urlsplit(target)
        port = parsed.port
    except ValueError:
        _add_error(errors, "target", "URL contains an invalid port.")
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        _add_error(errors, "target", "HTTP targets must use http:// or https://.")
    if not parsed.hostname:
        _add_error(errors, "target", "URL must include a hostname.")
    if parsed.username or parsed.password:
        _add_error(errors, "target", "Credentials are not allowed in target URLs.")
    if parsed.fragment:
        _add_error(errors, "target", "URL fragments are not allowed.")
    if port is not None and not 1 <= port <= 65_535:
        _add_error(errors, "target", "URL port must be between 1 and 65535.")

    hostname = parsed.hostname
    if hostname and not _valid_host(hostname, errors):
        return None
    if errors:
        return None

    normalized_host = hostname.lower().rstrip(".")
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    netloc = normalized_host if port is None else f"{normalized_host}:{port}"
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "", parsed.query, "")
    )


def _normalize_tcp_target(target: str, errors: dict[str, list[str]]) -> str | None:
    if any(token in target for token in ("://", "/", "@", "?", "#")):
        _add_error(errors, "target", "TCP targets must use host:port.")
        return None
    try:
        parsed = urlsplit(f"//{target}")
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        _add_error(
            errors,
            "target",
            "TCP target needs a valid port; write IPv6 as [address]:port.",
        )
        return None

    if not hostname or port is None:
        _add_error(errors, "target", "TCP targets must use host:port.")
        return None
    if not 1 <= port <= 65_535:
        _add_error(errors, "target", "TCP port must be between 1 and 65535.")
        return None
    if not _valid_host(hostname, errors):
        return None

    normalized_host = hostname.lower().rstrip(".")
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    return f"{normalized_host}:{port}"


def _normalize_ping_target(target: str, errors: dict[str, list[str]]) -> str | None:
    candidate = target.rstrip(".")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        if any(token in target for token in ("://", "/", "@", ":")):
            _add_error(errors, "target", "Ping targets must be a hostname or IP.")
            return None
        if not _valid_host(candidate, errors):
            return None
        return candidate.lower()

    if not _allowed_address(address, errors):
        return None
    return address.compressed


def _valid_host(host: str, errors: dict[str, list[str]]) -> bool:
    normalized = host.lower().rstrip(".")
    if normalized in DENIED_HOSTS:
        _add_error(errors, "target", "That metadata target is not allowed.")
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        if len(normalized) > 253 or not normalized:
            _add_error(errors, "target", "Hostname is invalid.")
            return False
        if normalized == "localhost":
            return True
        if not all(
            HOST_LABEL_PATTERN.fullmatch(label) for label in normalized.split(".")
        ):
            _add_error(errors, "target", "Hostname is invalid.")
            return False
        return True
    return _allowed_address(address, errors)


def _allowed_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    errors: dict[str, list[str]],
) -> bool:
    if str(address) in DENIED_HOSTS:
        _add_error(errors, "target", "That metadata target is not allowed.")
        return False
    if address.is_unspecified or address.is_multicast:
        _add_error(
            errors, "target", "Unspecified and multicast targets are not allowed."
        )
        return False
    return True


def _add_error(errors: dict[str, list[str]], field: str, message: str) -> None:
    errors.setdefault(field, []).append(message)
