import pytest

from app.models import CheckType
from app.validation import normalize_service_input


def valid_payload(**overrides):
    payload = {
        "name": "Example",
        "target": "https://example.com/health",
        "check_type": "http",
        "interval_seconds": 60,
        "expected_status_code": 200,
    }
    payload.update(overrides)
    return payload


def test_http_input_is_normalized():
    result, errors = normalize_service_input(
        valid_payload(name="  Website  ", target="HTTPS://EXAMPLE.COM:8443/health")
    )

    assert errors == {}
    assert result is not None
    assert result.name == "Website"
    assert result.target == "https://example.com:8443/health"
    assert result.check_type is CheckType.HTTP
    assert result.expected_status_code == 200


@pytest.mark.parametrize(
    ("target", "check_type", "normalized"),
    [
        ("NAS.LOCAL:443", "tcp_port", "nas.local:443"),
        ("[2001:db8::1]:22", "tcp_port", "[2001:db8::1]:22"),
        ("ROUTER.LOCAL", "ping", "router.local"),
        ("192.168.1.1", "ping", "192.168.1.1"),
    ],
)
def test_tcp_and_ping_targets(target, check_type, normalized):
    result, errors = normalize_service_input(
        valid_payload(target=target, check_type=check_type)
    )

    assert errors == {}
    assert result is not None
    assert result.target == normalized
    assert result.expected_status_code is None


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"name": ""}, "name"),
        ({"check_type": "udp"}, "check_type"),
        ({"interval_seconds": 5}, "interval_seconds"),
        ({"target": "example.com", "check_type": "http"}, "target"),
        ({"target": "http://user:secret@example.com"}, "target"),
        ({"target": "host:0", "check_type": "tcp_port"}, "target"),
        ({"target": "169.254.169.254", "check_type": "ping"}, "target"),
        ({"expected_status_code": 700}, "expected_status_code"),
    ],
)
def test_invalid_input_returns_field_errors(overrides, field):
    result, errors = normalize_service_input(valid_payload(**overrides))

    assert result is None
    assert field in errors
