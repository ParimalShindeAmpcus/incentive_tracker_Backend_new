"""GET /vlookup/template — description from canonical Hours Template definition."""

from fastapi.testclient import TestClient

from app.services.vlookup.template_definition import (
    HOURS_TEMPLATE_COLUMNS,
    HOURS_TEMPLATE_REQUIRED_COLUMNS,
    build_template_description_response,
    required_template_column_keys,
)


FORBIDDEN_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "database",
    "connection_string",
    "filesystem_path",
    "stack_trace",
    "traceback",
}


def test_template_description_requires_auth(client: TestClient):
    assert client.get("/api/v1/vlookup/template").status_code == 401


def test_template_description_ok_for_authenticated_user(
    client: TestClient, auth_headers: dict[str, str]
):
    response = client.get("/api/v1/vlookup/template", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["columns"] == HOURS_TEMPLATE_COLUMNS
    assert "message" in body
    assert FORBIDDEN_KEYS.isdisjoint({k.lower() for k in body.keys()})


def test_template_description_comes_from_canonical_definition():
    payload = build_template_description_response()
    assert payload["columns"] == HOURS_TEMPLATE_COLUMNS
    assert set(HOURS_TEMPLATE_REQUIRED_COLUMNS).issubset(set(HOURS_TEMPLATE_COLUMNS))


def test_upload_required_keys_match_canonical_required_columns():
    assert required_template_column_keys() == {"candidate_id", "candidate_name"}


def test_template_info_service_matches_canonical():
    from app.services.vlookup.vlookup_service import template_info

    info = template_info()
    assert info.columns == HOURS_TEMPLATE_COLUMNS
    assert info.message == build_template_description_response()["message"]
