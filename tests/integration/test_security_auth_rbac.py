"""Security & Access Control (RBAC & Auth) Integration Test Suite.

Tests cover:
- Unauthenticated vs Authenticated access across all API endpoints
- Token tampering, invalid signatures, expired tokens, and token type mismatches
- Role-Based Access Control (ADMIN, ACCOUNTS, VIEWER)
- Multi-user / role isolation and sensitive action protection
"""

import pytest
from datetime import datetime, timedelta, timezone
from jose import jwt
from fastapi.testclient import TestClient
from app.config import get_settings


class TestAuthenticationAndTokenSecurity:
    """Validate token verification, expiration, tampering, and denial on unauthenticated requests."""

    def test_unauthenticated_requests_denied_on_protected_endpoints(self, client: TestClient):
        """Protected endpoints must return 401 Unauthorized when Authorization header is absent."""
        endpoints = [
            ("POST", "/api/v1/cycles", {"incentive_month": "2026-09", "division": "NASHIK", "name": "Test"}),
            ("POST", "/api/v1/cycles/1/calculate", {}),
            ("POST", "/api/v1/cycles/1/approve", {"status": "APPROVED", "comments": "ok"}),
            ("DELETE", "/api/v1/cycles/1", None),
            ("GET", "/api/v1/audit/logs", None),
            ("POST", "/api/v1/coordinators", {"full_name": "Test", "email": "test@example.com", "organization": "Ampcus", "role_title": "CRM"}),
            ("GET", "/api/v1/auth/me", None),
        ]
        for method, path, payload in endpoints:
            if method == "POST":
                res = client.post(path, json=payload)
            elif method == "DELETE":
                res = client.delete(path)
            else:
                res = client.get(path)
            assert res.status_code == 401, f"Expected 401 for unauthenticated {method} {path}, got {res.status_code}"

    def test_tampered_jwt_signature_rejected(self, client: TestClient, auth_headers: dict):
        """Tampering with JWT signature or payload must result in 401 Unauthorized."""
        valid_token = auth_headers["Authorization"].split(" ")[1]
        parts = valid_token.split(".")
        # Tamper signature portion
        tampered_token = f"{parts[0]}.{parts[1]}.badsignature123"
        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
        assert res.status_code == 401
        assert "Invalid or expired token" in res.json().get("detail", "")

    def test_expired_jwt_rejected(self, client: TestClient):
        """An expired JWT token must be rejected with 401."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "1",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
        expired_token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert res.status_code == 401

    def test_refresh_token_rejected_on_access_protected_endpoint(self, client: TestClient):
        """Using a refresh token on an access-token protected endpoint must return 401."""
        login_res = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "Admin@123"})
        assert login_res.status_code == 200
        refresh_token = login_res.json()["refresh_token"]

        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
        assert res.status_code == 401
        assert "Invalid token type" in res.json().get("detail", "")

    def test_nonexistent_user_token_rejected(self, client: TestClient):
        """A token with a subject ID that does not exist in DB must be rejected."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "999999",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        orphan_token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {orphan_token}"})
        assert res.status_code == 401


class TestRoleBasedAccessControl:
    """Validate role-based permissions and boundaries for ADMIN, ACCOUNTS, and VIEWER roles."""

    def test_admin_can_perform_administrative_actions(self, client: TestClient, auth_headers: dict):
        """ADMIN has full administrative rights to create, calculate, and delete cycles."""
        # Create cycle
        create_res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "2026-10", "division": "ampcusTechInhouse", "name": "Admin Test Cycle"},
            headers=auth_headers,
        )
        assert create_res.status_code == 200, create_res.text
        cycle_id = create_res.json()["id"]

        # Calculate cycle
        calc_res = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert calc_res.status_code == 200

        # Delete cycle
        del_res = client.delete(f"/api/v1/cycles/{cycle_id}", headers=auth_headers)
        assert del_res.status_code == 200


    def test_viewer_access_audit(self, client: TestClient, viewer_headers: dict):
        """Audit VIEWER permissions: Viewer profile returns expected VIEWER role claim."""
        me_res = client.get("/api/v1/auth/me", headers=viewer_headers)
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "viewer@example.com"
        role_names = [r["name"] for r in me_res.json()["roles"]]
        assert "VIEWER" in role_names

    def test_accounts_operator_profile(self, client: TestClient, accounts_headers: dict):
        """Verify ACCOUNTS role identity and claims."""
        me_res = client.get("/api/v1/auth/me", headers=accounts_headers)
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "accounts@example.com"
        role_names = [r["name"] for r in me_res.json()["roles"]]
        assert "ACCOUNTS" in role_names

    def test_audit_viewer_role_boundaries(self, client: TestClient, viewer_headers: dict, auth_headers: dict):
        """Security Audit: Test if VIEWER is improperly permitted to perform privileged cycle operations."""
        # 1. Admin creates a cycle
        create_res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "2026-11", "division": "ampcusTechInhouse", "name": "RBAC Audit Cycle"},
            headers=auth_headers,
        )
        assert create_res.status_code == 200
        cycle_id = create_res.json()["id"]

        # 2. Verify that VIEWER is strictly rejected with 403 Forbidden on DELETE /api/v1/cycles/{id} (Fixed VULN-RBAC-001)
        del_res = client.delete(f"/api/v1/cycles/{cycle_id}", headers=viewer_headers)
        assert del_res.status_code == 403
        assert "Requires one of roles: ADMIN" in del_res.json()["detail"]


class TestEndpointAuthAudit:
    """Security Audit: Verify all critical candidate and cycle endpoints enforce authentication."""

    def test_audit_public_vs_protected_surface(self, client: TestClient):
        """Verify candidate and cycle endpoints reject unauthenticated access with 401 (Fixed VULN-AUTH-001)."""
        candidate_list_res = client.get("/api/v1/candidates")
        assert candidate_list_res.status_code == 401

        cycles_list_res = client.get("/api/v1/cycles")
        assert cycles_list_res.status_code == 401

        cycle_summary_res = client.get("/api/v1/cycles/1/summary")
        assert cycle_summary_res.status_code == 401

