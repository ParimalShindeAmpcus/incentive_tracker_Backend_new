"""Health endpoint tests — single canonical GET /health."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.health import health_service


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_does_not_expose_sensitive_fields(client):
    body = client.get("/health").json()
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


def test_duplicate_api_v1_health_route_removed(client):
    response = client.get("/api/v1/health")
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
