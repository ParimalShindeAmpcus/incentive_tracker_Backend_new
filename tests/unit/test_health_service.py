"""Example unit test for health service (stub)."""

from app.services.health import health_service


def test_check_health():
    result = health_service.check_health()
    assert result.status == "ok"
