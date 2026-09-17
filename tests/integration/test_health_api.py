"""Health endpoint tests — single canonical GET /health."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.health import health_service


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_does_not_expose_sensitive_fields():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/health")).json()
    forbidden = {
        "database_url",
        "secret",
        "password",
        "api_key",
        "token",
        "env",
        "environment",
        "config",
        "stack",
        "traceback",
        "path",
        "host",
        "ip",
    }
    lowered = {str(k).lower() for k in body.keys()}
    assert lowered.isdisjoint(forbidden)
    assert set(body.keys()) == {"status"}


@pytest.mark.asyncio
async def test_duplicate_api_v1_health_route_removed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 404


def test_openapi_has_single_health_path():
    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "get" in paths["/health"]
    assert "/api/v1/health" not in paths


def test_single_underlying_health_implementation():
    assert callable(health_service.check_health)
    result = health_service.check_health()
    assert result.status == "ok"
