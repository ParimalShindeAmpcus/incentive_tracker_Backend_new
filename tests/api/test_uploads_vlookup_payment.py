import io

import pandas as pd


def _xlsx_bytes(rows, columns):
    df = pd.DataFrame(rows, columns=columns)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_vlookup_match(client, auth_headers):
    cand_bytes = _xlsx_bytes(
        [{"Candidate ID": "V-1", "Candidate Name": "Pat Lee", "Client": "Globex", "Margin": 5}],
        ["Candidate ID", "Candidate Name", "Client", "Margin"],
    )
    r = client.post(
        "/api/v1/candidate-data/versions",
        headers=auth_headers,
        files={"file": ("c.xlsx", cand_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"division": "nashik"},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/v1/vlookup/match",
        headers=auth_headers,
        json={
            "division": "nashik",
            "rows": [
                {"candidate_id": "V-1", "candidate_name": "Pat Lee", "client": "Globex", "hours": 10},
                {"candidate_id": None, "candidate_name": "Unknown Person", "client": "X", "hours": 5},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched"] >= 1
    assert body["results"][0]["match_method"]
    assert body["results"][0]["match_result"]


def test_project_end_does_not_create_candidate(client, auth_headers):
    cand_bytes = _xlsx_bytes(
        [{"Candidate ID": "PE-1", "Candidate Name": "End User", "Client": "Acme", "Margin": 2}],
        ["Candidate ID", "Candidate Name", "Client", "Margin"],
    )
    assert client.post(
        "/api/v1/candidate-data/versions",
        headers=auth_headers,
        files={"file": ("c.xlsx", cand_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"division": "nashik"},
    ).status_code == 200

    before = client.get("/api/v1/candidates", headers=auth_headers).json()["meta"]["total"]
    pe_bytes = _xlsx_bytes(
        [{"Candidate ID": "PE-1", "Candidate Name": "End User", "Project End Date": "2026-06-01"}],
        ["Candidate ID", "Candidate Name", "Project End Date"],
    )
    r = client.post(
        "/api/v1/project-end/versions",
        headers=auth_headers,
        files={"file": ("pe.xlsx", pe_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"division": "nashik"},
    )
    assert r.status_code == 200, r.text
    after = client.get("/api/v1/candidates", headers=auth_headers).json()["meta"]["total"]
    assert after == before


def test_payment_endpoint_duplicate(client, auth_headers):
    # smoke: payment without line -> 404
    r = client.post(
        "/api/v1/payments",
        headers=auth_headers,
        json={"incentive_line_id": 999999},
    )
    assert r.status_code == 404
