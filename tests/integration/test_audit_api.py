"""Integration tests for audit trail API."""


def test_audit_logs_requires_auth(client):
    response = client.get("/api/v1/audit/logs")
    assert response.status_code == 401


def test_get_audit_logs_returns_frontend_shape(client, auth_headers):
    response = client.get("/api/v1/audit/logs", headers=auth_headers)
    assert response.status_code == 200
    logs = response.json()
    assert isinstance(logs, list)
    assert len(logs) >= 5

    first = logs[0]
    assert first["id"].startswith("LOG-")
    assert "timestamp" in first
    assert first["action"] in {
        "FILE_UPLOAD",
        "CANDIDATE_TOGGLE",
        "COORDINATOR_TOGGLE",
        "COORDINATOR_ADD",
        "HOURS_RECONCILIATION",
        "CALCULATION_RUN",
        "REPORT_EXPORT",
        "SYSTEM",
    }
    assert "title" in first
    assert "details" in first
    assert "user" in first
    assert "username" in first


def test_post_audit_log_creates_entry(client, auth_headers):
    payload = {
        "action": "CANDIDATE_TOGGLE",
        "title": "Candidate Incentive Inactivated",
        "details": "Changed CAND-001 status to Inactive",
        "metadata": {"candidateId": "CAND-001"},
    }
    create_response = client.post("/api/v1/audit/logs", json=payload, headers=auth_headers)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["action"] == "CANDIDATE_TOGGLE"
    assert created["title"] == payload["title"]
    assert created["id"].startswith("LOG-")

    list_response = client.get(
        "/api/v1/audit/logs",
        params={"action": "CANDIDATE_TOGGLE", "search": "CAND-001"},
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    matches = list_response.json()
    assert any(item["id"] == created["id"] for item in matches)


def test_invalid_action_returns_422(client, auth_headers):
    response = client.get(
        "/api/v1/audit/logs",
        params={"action": "NOT_A_REAL_ACTION"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_filter_by_action(client, auth_headers):
    response = client.get(
        "/api/v1/audit/logs",
        params={"action": "FILE_UPLOAD"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) >= 1
    assert all(log["action"] == "FILE_UPLOAD" for log in logs)
