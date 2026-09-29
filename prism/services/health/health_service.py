"""Health service — orchestration only (no HTTP)."""

from prism.models.health.schemas import HealthResponse
from prism.repositories.health import health_repository


def check_health() -> HealthResponse:
    status = health_repository.get_status()
    return HealthResponse(status=status)
