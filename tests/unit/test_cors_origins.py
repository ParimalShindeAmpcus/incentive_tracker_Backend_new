"""CORS allowlist security tests — no wildcard / permissive intranet origins."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture()
def cors_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def _preflight(client: TestClient, origin: str, method: str = "GET") -> object:
    return client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_get_cors_origins_comma_separated():
    settings = Settings(
        cors_origins="http://localhost:5173, http://127.0.0.1:5173, *"
    )
    assert settings.get_cors_origins() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_get_cors_origins_json_array():
    settings = Settings(
        cors_origins='["http://localhost:5173","http://127.0.0.1:5173","*"]'
    )
    assert settings.get_cors_origins() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_cors_allows_localhost_5173(cors_client: TestClient):
    response = _preflight(cors_client, "http://localhost:5173")
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_allows_127_0_0_1_5173(cors_client: TestClient):
    response = _preflight(cors_client, "http://127.0.0.1:5173")
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_cors_rejects_untrusted_public_origin(cors_client: TestClient):
    response = _preflight(cors_client, "http://evil.example.com")
    assert "access-control-allow-origin" not in response.headers


def test_cors_rejects_arbitrary_intranet_origin(cors_client: TestClient):
    response = _preflight(cors_client, "http://192.168.1.50:5173")
    assert "access-control-allow-origin" not in response.headers


def test_cors_rejects_arbitrary_localhost_port(cors_client: TestClient):
    response = _preflight(cors_client, "http://localhost:9999")
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_allows_expected_methods_and_headers(cors_client: TestClient):
    response = _preflight(cors_client, "http://localhost:5173", method="POST")
    assert response.status_code in {200, 204}
    allowed_methods = (response.headers.get("access-control-allow-methods") or "").upper()
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
        assert method in allowed_methods
    allowed_headers = (response.headers.get("access-control-allow-headers") or "").lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


def test_authenticated_request_from_allowed_origin_keeps_cors(
    client: TestClient,
    auth_headers: dict[str, str],
):
    response = client.get(
        "/api/v1/candidates",
        headers={**auth_headers, "Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_create_app_has_no_intranet_cors_regex(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    get_settings.cache_clear()
    app = create_app()
    get_settings.cache_clear()

    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            cors_middleware = middleware
            break
    assert cors_middleware is not None
    options = getattr(cors_middleware, "options", None) or getattr(cors_middleware, "kwargs", {})
    assert options.get("allow_origin_regex") in (None, "")
    assert "*" not in (options.get("allow_origins") or [])
    for origin in options.get("allow_origins") or []:
        assert "192.168." not in origin
        assert not origin.startswith("http://10.")
