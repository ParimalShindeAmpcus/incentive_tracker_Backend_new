"""Unit tests for SEC-16: Security headers middleware.

Verifies that all required security headers are properly stamped onto API responses:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: strict-origin-when-cross-origin
  - X-XSS-Protection: 1; mode=block
  - Strict-Transport-Security: max-age=...; includeSubDomains
  - Content-Security-Policy: default-src 'self'; ...
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app, SecurityHeadersMiddleware
from app.security.headers import DEFAULT_CSP_POLICY


@pytest.fixture()
def client():
    """Test client for the main application."""
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_all_security_headers_present_on_health_and_root(client: TestClient):
    """Verify all 6 required security headers are stamped on successful responses."""
    for path in ("/health", "/"):
        response = client.get(path)
        assert response.status_code == 200

        headers = response.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Strict-Transport-Security" in headers
        assert "max-age=" in headers["Strict-Transport-Security"]
        assert "includeSubDomains" in headers["Strict-Transport-Security"]

        csp = headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp


def test_security_headers_present_on_error_responses(client: TestClient):
    """Verify security headers are attached to 404 and 401 error responses."""
    # 404 Not Found
    resp_404 = client.get("/api/v1/nonexistent-endpoint-xyz")
    assert resp_404.status_code == 404
    assert resp_404.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp_404.headers.get("X-Frame-Options") == "DENY"
    assert resp_404.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert resp_404.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "Strict-Transport-Security" in resp_404.headers
    assert "Content-Security-Policy" in resp_404.headers

    # 401 Unauthorized
    resp_401 = client.get("/api/v1/candidates")
    assert resp_401.status_code == 401
    assert resp_401.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp_401.headers.get("X-Frame-Options") == "DENY"
    assert resp_401.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert resp_401.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "Strict-Transport-Security" in resp_401.headers
    assert "Content-Security-Policy" in resp_401.headers


def test_security_headers_on_cors_preflight(client: TestClient):
    """Verify security headers are preserved on OPTIONS preflight responses."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "Strict-Transport-Security" in response.headers
    assert "Content-Security-Policy" in response.headers


def test_docs_and_redoc_endpoints_accessible_with_csp(client: TestClient):
    """Verify FastAPI /docs and /redoc are accessible and include the CSP header."""
    for docs_path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(docs_path)
        assert response.status_code == 200
        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]
        assert "cdn.jsdelivr.net" in csp


def test_custom_csp_policy():
    """Verify custom CSP policy can be provided."""
    custom_csp = "default-src 'self'; script-src 'self'"
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, csp_policy=custom_csp)

    @app.get("/ping")
    def ping():
        return {"ping": "pong"}

    with TestClient(app) as test_client:
        resp = test_client.get("/ping")
        assert resp.headers.get("Content-Security-Policy") == custom_csp


def test_hsts_disabled_toggle():
    """Verify HSTS can be disabled via hsts_enabled=False for plain HTTP."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=False)

    @app.get("/ping")
    def ping():
        return {"ping": "pong"}

    with TestClient(app) as test_client:
        resp = test_client.get("/ping")
        assert "Strict-Transport-Security" not in resp.headers


def test_hsts_sent_over_https_even_when_disabled_for_http():
    """Verify HSTS is automatically sent when request is over HTTPS/X-Forwarded-Proto."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=False)

    @app.get("/ping")
    def ping():
        return {"ping": "pong"}

    with TestClient(app) as test_client:
        resp = test_client.get("/ping", headers={"X-Forwarded-Proto": "https"})
        assert "Strict-Transport-Security" in resp.headers
