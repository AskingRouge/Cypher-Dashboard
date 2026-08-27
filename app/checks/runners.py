from __future__ import annotations

import socket
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlsplit

import ping3
import requests

from app.models import CheckType

USER_AGENT = "HomeLabDashboard/1.0"
MAX_ERROR_LENGTH = 500


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    is_up: bool
    response_time_ms: float | None
    status_code: int | None = None
    error_message: str | None = None


def run_check(
    *,
    check_type: CheckType,
    target: str,
    expected_status_code: int | None,
    timeout_seconds: float,
) -> CheckOutcome:
    """Dispatch one health check without allowing network failures to escape."""
    if check_type is CheckType.HTTP:
        return run_http_check(
            target,
            expected_status_code=expected_status_code or 200,
            timeout_seconds=timeout_seconds,
        )
    if check_type is CheckType.TCP_PORT:
        return run_tcp_check(target, timeout_seconds=timeout_seconds)
    if check_type is CheckType.PING:
        return run_ping_check(target, timeout_seconds=timeout_seconds)
    raise ValueError(f"Unsupported check type: {check_type}")


def run_http_check(
    target: str, *, expected_status_code: int, timeout_seconds: float
) -> CheckOutcome:
    started = perf_counter()
    response = None
    try:
        response = requests.get(
            target,
            timeout=timeout_seconds,
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": USER_AGENT},
        )
        elapsed_ms = _elapsed_ms(started)
        is_up = response.status_code == expected_status_code
        error = None
        if not is_up:
            error = (
                f"Expected HTTP {expected_status_code}, "
                f"received {response.status_code}."
            )
        return CheckOutcome(
            is_up=is_up,
            response_time_ms=elapsed_ms,
            status_code=response.status_code,
            error_message=error,
        )
    except requests.RequestException as exc:
        return CheckOutcome(
            is_up=False,
            response_time_ms=_elapsed_ms(started),
            error_message=_safe_error(exc),
        )
    finally:
        if response is not None:
            response.close()


def run_tcp_check(target: str, *, timeout_seconds: float) -> CheckOutcome:
    parsed = urlsplit(f"//{target}")
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        raise ValueError(f"Invalid normalized TCP target: {target}")

    started = perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return CheckOutcome(is_up=True, response_time_ms=_elapsed_ms(started))
    except (TimeoutError, ConnectionError, socket.gaierror, OSError) as exc:
        return CheckOutcome(
            is_up=False,
            response_time_ms=_elapsed_ms(started),
            error_message=_safe_error(exc),
        )


def run_ping_check(target: str, *, timeout_seconds: float) -> CheckOutcome:
    started = perf_counter()
    try:
        latency_ms = ping3.ping(target, timeout=timeout_seconds, unit="ms")
        if latency_ms is None or latency_ms is False:
            return CheckOutcome(
                is_up=False,
                response_time_ms=_elapsed_ms(started),
                error_message="Host did not reply before the ping timeout.",
            )
        return CheckOutcome(is_up=True, response_time_ms=float(latency_ms))
    except (PermissionError, OSError) as exc:
        message = _safe_error(exc)
        if isinstance(exc, PermissionError):
            message = f"ICMP permission denied: {message}"
        return CheckOutcome(
            is_up=False,
            response_time_ms=_elapsed_ms(started),
            error_message=message,
        )


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _safe_error(error: BaseException) -> str:
    message = str(error).strip() or error.__class__.__name__
    return message[:MAX_ERROR_LENGTH]
