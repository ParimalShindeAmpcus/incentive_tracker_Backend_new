"""Health HTTP routes — thin controller layer only."""

from fastapi import APIRouter

from app.models.health.schemas import HealthResponse
from app.services.health import health_service

router = APIRouter()


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """GET /health — wired controller → service → repository."""
    return health_service.check_health()
