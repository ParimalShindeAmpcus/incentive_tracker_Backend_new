"""Canonical Consolidated File listing — no deprecated /messy-file duplicate route."""

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_has_consolidated_file_not_messy_file_list():
    paths = app.openapi()["paths"]
    assert "/api/v1/vlookup/consolidated-file" in paths
    assert "get" in paths["/api/v1/vlookup/consolidated-file"]
    assert "/api/v1/vlookup/messy-file" not in paths


def test_consolidated_file_list_requires_auth(client: TestClient):
    response = client.get("/api/v1/vlookup/consolidated-file")
    assert response.status_code == 401


def test_consolidated_file_list_works_for_authorized_user(
    client: TestClient, auth_headers: dict[str, str]
):
    response = client.get("/api/v1/vlookup/consolidated-file", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "batch_id" in body
    assert "count" in body
    assert "identities" in body
    assert isinstance(body["identities"], list)


def test_deprecated_messy_file_list_route_removed(
    client: TestClient, auth_headers: dict[str, str]
):
    response = client.get("/api/v1/vlookup/messy-file", headers=auth_headers)
    assert response.status_code == 404


def test_single_list_messy_file_service_implementation():
    """Only one underlying consolidated-file listing service should exist."""
    from app.services.vlookup import vlookup_service

    assert hasattr(vlookup_service, "list_messy_file")
    assert not hasattr(vlookup_service, "list_consolidated_file") or (
        vlookup_service.list_consolidated_file is vlookup_service.list_messy_file
    )
