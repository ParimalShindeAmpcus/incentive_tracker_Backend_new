"""Health service — orchestration only (no HTTP)."""

from app.models.health.schemas import HealthResponse
from app.repositories.health import health_repository


def check_health() -> HealthResponse:
    status = health_repository.get_status()
    return HealthResponse(status=status)
