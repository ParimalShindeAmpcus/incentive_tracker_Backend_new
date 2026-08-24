"""Integration tests for audit trail API."""


def test_audit_logs_requires_auth(client):
    response = client.get("/api/v1/audit/logs")
    assert response.status_code == 401


def test_get_audit_logs_starts_empty(client, auth_headers):
    response = client.get("/api/v1/audit/logs", headers=auth_headers)
    assert response.status_code == 200
    logs = response.json()
    assert isinstance(logs, list)
    assert logs == []


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
    assert "timestamp" in created
    assert "user" in created
    assert "username" in created

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
    client.post(
        "/api/v1/audit/logs",
        json={
            "action": "FILE_UPLOAD",
            "title": "Uploaded Candidate Dataset",
            "details": "Imported 2 candidate records",
        },
        headers=auth_headers,
    )
    client.post(
        "/api/v1/audit/logs",
        json={
            "action": "CALCULATION_RUN",
            "title": "Ran Cycle Calculation",
            "details": "Calculated incentives for 2026-07",
        },
        headers=auth_headers,
    )
    response = client.get(
        "/api/v1/audit/logs",
        params={"action": "FILE_UPLOAD"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) >= 1
    assert all(log["action"] == "FILE_UPLOAD" for log in logs)


def test_new_action_types_are_accepted(client, auth_headers):
    for action, title in (
        ("FILE_DOWNLOAD", "Downloaded Candidate Master Excel"),
        ("CANDIDATE_ADD", "Added 3 candidate(s)"),
        ("CANDIDATE_UPDATE", "Updated candidate Jane Doe"),
        ("CYCLE_APPROVE", "Approved cycle 2026-08"),
        ("CYCLE_CANCEL", "Cancelled cycle 2026-08"),
        ("PAYMENT_UPDATE", "Updated payment status for Jane Doe"),
        ("COORDINATOR_DELETE", "Deleted left coordinator Jane Doe"),
    ):
        response = client.post(
            "/api/v1/audit/logs",
            json={"action": action, "title": title, "details": f"Test {action}"},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["action"] == action

        listed = client.get(
            "/api/v1/audit/logs",
            params={"action": action},
            headers=auth_headers,
        )
        assert listed.status_code == 200
        assert all(item["action"] == action for item in listed.json())
        assert any(item["title"] == title for item in listed.json())


def test_create_coordinator_writes_coordinator_add(client, auth_headers):
    response = client.post(
        "/api/v1/coordinators",
        json={
            "full_name": "Audit Trail Coordinator",
            "email": "audit.trail.coordinator@example.com",
            "organization": "Ampcus",
            "role_title": "CRM",
            "employment_status": "ACTIVE",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    logs = client.get(
        "/api/v1/audit/logs",
        params={"action": "COORDINATOR_ADD", "search": "Audit Trail Coordinator"},
        headers=auth_headers,
    )
    assert logs.status_code == 200
    matches = logs.json()
    assert matches, "creating a coordinator should write COORDINATOR_ADD"
    assert all(item["action"] == "COORDINATOR_ADD" for item in matches)
    assert any("Audit Trail Coordinator" in (item["title"] + item["details"]) for item in matches)


def test_delete_cycle_writes_cycle_cancel(client, auth_headers):
    # 1. Create a cycle
    create_res = client.post(
        "/api/v1/cycles",
        json={
            "incentive_month": "2026-09",
            "division": "NASHIK",
            "name": "September 2026 Nashik Cycle",
        },
        headers=auth_headers,
    )
    assert create_res.status_code == 200, create_res.text
    cycle_id = create_res.json()["id"]

    # 2. Delete (cancel) the cycle
    del_res = client.delete(f"/api/v1/cycles/{cycle_id}", headers=auth_headers)
    assert del_res.status_code == 200, del_res.text
    assert del_res.json()["message"] == "deleted"

    # 3. Verify audit log has CYCLE_CANCEL entry
    logs_res = client.get(
        "/api/v1/audit/logs",
        params={"action": "CYCLE_CANCEL", "search": str(cycle_id)},
        headers=auth_headers,
    )
    assert logs_res.status_code == 200
    entries = logs_res.json()
    assert len(entries) >= 1
    assert any(e["action"] == "CYCLE_CANCEL" and str(cycle_id) in (e["title"] + e["details"] + str(e.get("metadata") or "")) for e in entries)
