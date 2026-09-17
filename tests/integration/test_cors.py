import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_cors_trusted_origin_allowed():
    """Verify that a trusted origin (e.g. from the parsed env file) receives the appropriate CORS headers on preflight."""
    # Assuming http://localhost:5173 is in the configured test origins (which it should be by default)
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization"
    }
    response = client.options("/api/v1/health", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_private_ip_rejected():
    """Verify that an arbitrary private IP is rejected and does NOT receive the permissive CORS headers."""
    headers = {
        "Origin": "http://192.168.1.100:3000",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization"
    }
    response = client.options("/api/v1/health", headers=headers)
    assert response.status_code == 400


def test_cors_other_private_ips_rejected():
    """Verify other private IP ranges are rejected."""
    for origin in [
        "http://10.0.0.25:8080",
        "http://172.16.1.20:3000",
        "http://172.31.255.100:5173",
        "http://0.0.0.0:8000"
    ]:
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "GET"
        }
        response = client.options("/api/v1/health", headers=headers)
        assert response.status_code == 400


def test_cors_external_domain_rejected():
    """Verify arbitrary external domains are rejected."""
    headers = {
        "Origin": "https://evil-example.com",
        "Access-Control-Request-Method": "GET"
    }
    response = client.options("/api/v1/health", headers=headers)
    assert response.status_code == 400

