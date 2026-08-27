import socket

import pytest
import requests

from app.checks.runners import (
    run_check,
    run_http_check,
    run_ping_check,
    run_tcp_check,
)
from app.models import CheckType


class DummyResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


class DummySocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_http_expected_status_is_up(monkeypatch):
    response = DummyResponse(204)

    def fake_get(*args, **kwargs):
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        assert kwargs["timeout"] == 5
        return response

    monkeypatch.setattr("app.checks.runners.requests.get", fake_get)

    outcome = run_http_check(
        "https://example.com", expected_status_code=204, timeout_seconds=5
    )

    assert outcome.is_up is True
    assert outcome.status_code == 204
    assert outcome.response_time_ms is not None
    assert response.closed is True


def test_http_unexpected_status_is_down(monkeypatch):
    monkeypatch.setattr(
        "app.checks.runners.requests.get", lambda *args, **kwargs: DummyResponse(503)
    )

    outcome = run_http_check(
        "https://example.com", expected_status_code=200, timeout_seconds=5
    )

    assert outcome.is_up is False
    assert outcome.status_code == 503
    assert "Expected HTTP 200" in outcome.error_message


def test_http_network_failure_becomes_outcome(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.Timeout("request timed out")

    monkeypatch.setattr("app.checks.runners.requests.get", fail)

    outcome = run_http_check(
        "https://example.com", expected_status_code=200, timeout_seconds=1
    )

    assert outcome.is_up is False
    assert outcome.status_code is None
    assert "timed out" in outcome.error_message


def test_tcp_success_and_refusal(monkeypatch):
    monkeypatch.setattr(
        "app.checks.runners.socket.create_connection",
        lambda address, timeout: DummySocket(),
    )
    assert run_tcp_check("router.local:22", timeout_seconds=2).is_up is True

    def refuse(address, timeout):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr("app.checks.runners.socket.create_connection", refuse)
    outcome = run_tcp_check("router.local:22", timeout_seconds=2)
    assert outcome.is_up is False
    assert "refused" in outcome.error_message


def test_tcp_dns_failure_becomes_outcome(monkeypatch):
    def fail(address, timeout):
        raise socket.gaierror("name not known")

    monkeypatch.setattr("app.checks.runners.socket.create_connection", fail)

    outcome = run_tcp_check("missing.local:443", timeout_seconds=2)

    assert outcome.is_up is False
    assert "name not known" in outcome.error_message


def test_ping_success_timeout_and_permission(monkeypatch):
    monkeypatch.setattr("app.checks.runners.ping3.ping", lambda *args, **kwargs: 4.25)
    outcome = run_ping_check("router.local", timeout_seconds=2)
    assert outcome.is_up is True
    assert outcome.response_time_ms == 4.25

    monkeypatch.setattr("app.checks.runners.ping3.ping", lambda *args, **kwargs: None)
    assert run_ping_check("router.local", timeout_seconds=2).is_up is False

    def denied(*args, **kwargs):
        raise PermissionError("operation not permitted")

    monkeypatch.setattr("app.checks.runners.ping3.ping", denied)
    outcome = run_ping_check("router.local", timeout_seconds=2)
    assert outcome.is_up is False
    assert "ICMP permission denied" in outcome.error_message


def test_dispatcher_rejects_unsupported_type():
    with pytest.raises(ValueError):
        run_check(
            check_type="udp",
            target="example.com",
            expected_status_code=None,
            timeout_seconds=2,
        )


def test_dispatcher_defaults_http_status_to_200(monkeypatch):
    captured = {}

    def fake_http(target, *, expected_status_code, timeout_seconds):
        captured["status"] = expected_status_code
        return run_ping_check("unused", timeout_seconds=timeout_seconds)

    monkeypatch.setattr("app.checks.runners.run_http_check", fake_http)
    monkeypatch.setattr("app.checks.runners.ping3.ping", lambda *args, **kwargs: 1.0)

    run_check(
        check_type=CheckType.HTTP,
        target="https://example.com",
        expected_status_code=None,
        timeout_seconds=2,
    )

    assert captured["status"] == 200
