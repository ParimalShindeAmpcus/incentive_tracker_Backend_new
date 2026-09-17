"""Comprehensive integration tests for all 7 security audit items:
1. Candidate PATCH Role Check
2. CSV / Excel Formula Injection Protection
3. Proprietary Incentive Slabs Authorization
4. Published Hours Data Access Control
5. Personnel Directory (Coordinators) Protection
6. Refresh Token Device / Client Fingerprint Binding
7. Stateless Logout / Token Blacklisting
"""

import pytest
from fastapi.testclient import TestClient

from app.core.sanitization import sanitize_excel_cell


def test_item1_candidate_patch_and_version_role_checks(client: TestClient):
    """1. Candidate PATCH and version creation require authentication & admin role."""
    unauthed = TestClient(client.app)
    # Unauthenticated PATCH
    patch_resp = unauthed.patch("/api/v1/candidates/1", json={"candidate_name": "Hacked Name"})
    assert patch_resp.status_code == 401, f"Expected 401, got {patch_resp.status_code}: {patch_resp.text}"

    # Unauthenticated version create
    version_resp = unauthed.post("/api/v1/candidate-data/versions", json={"version_name": "v_test", "division": "nashik", "records": []})
    assert version_resp.status_code == 401, f"Expected 401, got {version_resp.status_code}: {version_resp.text}"

    # Authenticated Admin login
    admin_client = TestClient(client.app)
    login_resp = admin_client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "Admin@123"})
    assert login_resp.status_code == 200

    # Authenticated Admin PATCH (404 expected for nonexistent candidate)
    auth_patch_resp = admin_client.patch(
        "/api/v1/candidates/99999",
        json={"candidate_name": "Test Candidate"},
    )
    assert auth_patch_resp.status_code == 404, f"Expected 404 for nonexistent candidate, got {auth_patch_resp.status_code}"


def test_item2_formula_injection_sanitization():
    """2. CSV/Excel cell sanitizer neutralizes formulas (=, +, -, @, \\t, \\r)."""
    assert sanitize_excel_cell("=cmd|'/C calc'!A0") == "'=cmd|'/C calc'!A0"
    assert sanitize_excel_cell("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_excel_cell("+1+2") == "'+1+2"
    assert sanitize_excel_cell("-5+2") == "'-5+2"
    assert sanitize_excel_cell("@HYPERLINK('http://evil.com')") == "'@HYPERLINK('http://evil.com')"
    assert sanitize_excel_cell("\tDangerousTab") == "'\tDangerousTab"
    assert sanitize_excel_cell("\rDangerousCR") == "'\rDangerousCR"
    assert sanitize_excel_cell("  =IndentedFormula") == "'  =IndentedFormula"
    
    # Harmless values unchanged
    assert sanitize_excel_cell("John Doe") == "John Doe"
    assert sanitize_excel_cell(12345) == 12345
    assert sanitize_excel_cell(None) is None


def test_item3_proprietary_incentive_slabs_protection(client: TestClient):
    """3. Proprietary incentive slabs are protected from unauthenticated access."""
    unauthed = TestClient(client.app)
    unauth_resp = unauthed.get("/api/v1/incentive-slabs")
    assert unauth_resp.status_code == 401, f"Expected 401, got {unauth_resp.status_code}: {unauth_resp.text}"

    # Authenticated admin access succeeds
    admin_client = TestClient(client.app)
    login_resp = admin_client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "Admin@123"})
    assert login_resp.status_code == 200

    auth_resp = admin_client.get("/api/v1/incentive-slabs")
    assert auth_resp.status_code == 200, f"Expected 200, got {auth_resp.status_code}: {auth_resp.text}"
    assert isinstance(auth_resp.json(), list)


def test_item4_published_hours_data_protection(client: TestClient):
    """4. Published hours data and mutation endpoints are strictly authenticated."""
    unauthed = TestClient(client.app)
    # Unauthenticated access to published hours rejected
    pub_resp = unauthed.get("/api/v1/hours-data/published?month=2026-07")
    assert pub_resp.status_code == 401, f"Expected 401, got {pub_resp.status_code}: {pub_resp.text}"

    # Unauthenticated hours version create rejected
    ver_resp = unauthed.post("/api/v1/hours-data/versions", json={"division": "nashik", "month": "2026-07", "rows": []})
    assert ver_resp.status_code == 401, f"Expected 401, got {ver_resp.status_code}: {ver_resp.text}"

    # Unauthenticated row patch rejected
    row_resp = unauthed.patch("/api/v1/hours-data/rows/1", json={"hours_worked": 160})
    assert row_resp.status_code == 401, f"Expected 401, got {row_resp.status_code}: {row_resp.text}"

    # Authenticated access to published hours
    admin_client = TestClient(client.app)
    login_resp = admin_client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "Admin@123"})
    assert login_resp.status_code == 200

    auth_pub = admin_client.get("/api/v1/hours-data/published?month=2026-07")
    assert auth_pub.status_code == 200, f"Expected 200, got {auth_pub.status_code}: {auth_pub.text}"


def test_item5_personnel_directory_protection(client: TestClient):
    """5. Personnel directories (coordinators, organizations, divisions) require authentication."""
    unauthed = TestClient(client.app)
    # Coordinators list
    coord_resp = unauthed.get("/api/v1/coordinators")
    assert coord_resp.status_code == 401, f"Expected 401, got {coord_resp.status_code}: {coord_resp.text}"

    # Coordinators summary
    summary_resp = unauthed.get("/api/v1/coordinators/summary")
    assert summary_resp.status_code == 401, f"Expected 401, got {summary_resp.status_code}: {summary_resp.text}"

    # Divisions & Organizations
    div_resp = unauthed.get("/api/v1/divisions")
    assert div_resp.status_code == 401, f"Expected 401, got {div_resp.status_code}: {div_resp.text}"

    org_resp = unauthed.get("/api/v1/organizations")
    assert org_resp.status_code == 401, f"Expected 401, got {org_resp.status_code}: {org_resp.text}"

    # Authenticated coordinator list succeeds
    admin_client = TestClient(client.app)
    login_resp = admin_client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "Admin@123"})
    assert login_resp.status_code == 200

    auth_coord = admin_client.get("/api/v1/coordinators")
    assert auth_coord.status_code == 200, f"Expected 200, got {auth_coord.status_code}: {auth_coord.text}"


def test_item6_refresh_token_device_fingerprint_binding(client: TestClient):
    """6. Refresh tokens are bound to client device/User-Agent fingerprint and rejected if stolen/replayed."""
    device_a_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}
    device_b_headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) Safari/604.1"}

    # 1. Login from Device A
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
        headers=device_a_headers,
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.cookies.get("refresh_token")
    assert refresh_token is not None

    # 2. Attempt refresh from Device B (Mismatched fingerprint / Stolen token)
    attacker_client = TestClient(client.app, cookies={"refresh_token": refresh_token})
    attacker_resp = attacker_client.post("/api/v1/auth/refresh", headers=device_b_headers)
    assert attacker_resp.status_code == 401
    assert "fingerprint mismatch" in attacker_resp.text.lower() or "revoked" in attacker_resp.text.lower()

    # 3. Subsequent refresh on Device A also fails because token was revoked upon theft attempt
    legit_client = TestClient(client.app, cookies={"refresh_token": refresh_token})
    subsequent_resp = legit_client.post("/api/v1/auth/refresh", headers=device_a_headers)
    assert subsequent_resp.status_code == 401


def test_item7_stateless_logout_and_token_blacklisting(client: TestClient):
    """7. Logout immediately revokes both access and refresh tokens."""
    # 1. Login
    login_client = TestClient(client.app)
    login_resp = login_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.cookies.get("access_token")
    refresh_token = login_resp.cookies.get("refresh_token")
    assert access_token and refresh_token

    # 2. Verify active access token works
    authed_client = TestClient(client.app, cookies={"access_token": access_token, "refresh_token": refresh_token})
    me_resp = authed_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200

    # 3. Perform logout
    logout_resp = authed_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # 4. Attempt to reuse old access token after logout -> Must return 401
    reused_client = TestClient(client.app, cookies={"access_token": access_token})
    me_after_logout = reused_client.get("/api/v1/auth/me")
    assert me_after_logout.status_code == 401, f"Expected 401 for revoked access token, got {me_after_logout.status_code}"

    # Also test via Authorization: Bearer header
    header_client = TestClient(client.app)
    me_header_after = header_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_header_after.status_code == 401, f"Expected 401 for revoked header token, got {me_header_after.status_code}"

    # 5. Attempt to refresh with old refresh token after logout -> Must return 401
    refresh_client = TestClient(client.app, cookies={"refresh_token": refresh_token})
    refresh_after_logout = refresh_client.post("/api/v1/auth/refresh")
    assert refresh_after_logout.status_code == 401, f"Expected 401 for revoked refresh token, got {refresh_after_logout.status_code}"
