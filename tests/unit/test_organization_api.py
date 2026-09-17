"""Organization / division hierarchy API security tests."""

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.repositories.auth import auth_repository
from app.repositories.organization import organization_repository
from app.security.auth import hash_password


ALLOWED_ORG_FIELDS = {"id", "code", "name", "is_active", "created_at"}
ALLOWED_DIV_FIELDS = {"id", "organization_id", "code", "name", "is_active", "created_at"}
FORBIDDEN_KEYS = {
    "password",
    "hashed_password",
    "secret",
    "token",
    "api_key",
    "database_url",
}


def _create_viewer_and_login(client: TestClient) -> dict[str, str]:
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        viewer_role = auth_repository.get_role_by_name(db, "VIEWER")
        assert viewer_role is not None
        existing = auth_repository.get_user_by_email(db, "viewer@example.com")
        if existing is None:
            auth_repository.create_user(
                db,
                email="viewer@example.com",
                full_name="Viewer User",
                hashed_password=hash_password("Viewer@123"),
                roles=[viewer_role],
                is_active=True,
            )
        db.commit()
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "Viewer@123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_organizations_requires_auth(client: TestClient):
    assert client.get("/api/v1/organizations").status_code == 401


def test_divisions_requires_auth(client: TestClient):
    assert client.get("/api/v1/divisions").status_code == 401


def test_organizations_forbidden_for_viewer(client: TestClient):
    headers = _create_viewer_and_login(client)
    response = client.get("/api/v1/organizations", headers=headers)
    assert response.status_code == 403, response.text


def test_divisions_forbidden_for_viewer(client: TestClient):
    headers = _create_viewer_and_login(client)
    response = client.get("/api/v1/divisions", headers=headers)
    assert response.status_code == 403, response.text


def test_organizations_ok_for_admin(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/v1/organizations", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    for row in body:
        assert set(row.keys()) <= ALLOWED_ORG_FIELDS
        assert FORBIDDEN_KEYS.isdisjoint(row.keys())
        assert row["is_active"] is True


def test_divisions_ok_for_admin(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/v1/divisions", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    for row in body:
        assert set(row.keys()) <= ALLOWED_DIV_FIELDS
        assert FORBIDDEN_KEYS.isdisjoint(row.keys())
        assert row["is_active"] is True


def test_divisions_filter_by_valid_organization(
    client: TestClient, auth_headers: dict[str, str]
):
    orgs = client.get("/api/v1/organizations", headers=auth_headers).json()
    org_id = orgs[0]["id"]
    response = client.get(
        f"/api/v1/divisions?organization_id={org_id}", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    for row in response.json():
        assert row["organization_id"] == org_id


def test_divisions_unknown_organization_id_returns_404(
    client: TestClient, auth_headers: dict[str, str]
):
    response = client.get(
        "/api/v1/divisions?organization_id=999999", headers=auth_headers
    )
    assert response.status_code == 404
    assert "Organization not found" in response.text


def test_inactive_organization_filter_returns_404(
    client: TestClient, auth_headers: dict[str, str]
):
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        inactive = organization_repository.create_organization(
            db, code="INACTIVE_ORG", name="Inactive Org"
        )
        inactive.is_active = False
        db.commit()
        inactive_id = inactive.id
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    response = client.get(
        f"/api/v1/divisions?organization_id={inactive_id}", headers=auth_headers
    )
    assert response.status_code == 404
