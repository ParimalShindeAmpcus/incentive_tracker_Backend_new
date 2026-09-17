"""Root endpoint — no unnecessary information disclosure."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


FORBIDDEN_KEYS = {
    "app",
    "docs",
    "redoc",
    "openapi",
    "api",
    "health",
    "version",
    "environment",
    "debug",
    "password",
    "secret",
    "token",
    "api_key",
    "database",
    "db_host",
    "python_version",
    "framework_version",
    "internal_ip",
    "file_path",
    "traceback",
    "stack",
}


@pytest.mark.asyncio
async def test_root_returns_minimal_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root_does_not_disclose_internal_fields():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/")).json()
    assert set(body.keys()) == {"status"}
    assert FORBIDDEN_KEYS.isdisjoint({k.lower() for k in body.keys()})


@pytest.mark.asyncio
async def test_health_unchanged_and_separate_from_root():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        root = await client.get("/")
        health = await client.get("/health")
    assert root.json() == {"status": "ok"}
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
