import io

import pandas as pd


def _xlsx_bytes(rows, columns):
    df = pd.DataFrame(rows, columns=columns)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_cycle_calculate_approve_pay_flow(client, auth_headers):
    # 1) Upload candidates
    cand_bytes = _xlsx_bytes(
        [
            {
                "Candidate ID": "C-100",
                "Candidate Name": "Alice Smith",
                "Client": "Acme",
                "Margin": 3.5,
                "Start Date": "2026-01-01",
                "Recruiter": "Bob Recruiter",
                "Team Lead": "Tina Lead",
                "Contract Type": "W2",
            }
        ],
        [
            "Candidate ID",
            "Candidate Name",
            "Client",
            "Margin",
            "Start Date",
            "Recruiter",
            "Team Lead",
            "Contract Type",
        ],
    )
    r = client.post(
        "/api/v1/candidate-data/versions",
        headers=auth_headers,
        files={"file": ("cand.xlsx", cand_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"division": "nashik", "version_label": "cand-v1"},
    )
    assert r.status_code == 200, r.text
    cand_version = r.json()["version"]["id"]
    assert r.json()["created_candidates"] >= 1

    # 2) Hours upload (must not create candidates)
    before = client.get("/api/v1/candidates", headers=auth_headers).json()["meta"]["total"]
    hours_bytes = _xlsx_bytes(
        [{"Candidate ID": "C-100", "Candidate Name": "Alice Smith", "Client": "Acme", "Hours": 160, "Date": "2026-07-15"}],
        ["Candidate ID", "Candidate Name", "Client", "Hours", "Date"],
    )
    r = client.post(
        "/api/v1/hours-data/versions",
        headers=auth_headers,
        files={"file": ("hours.xlsx", hours_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"division": "nashik"},
    )
    assert r.status_code == 200, r.text
    hours_version = r.json()["version"]["id"]
    after = client.get("/api/v1/candidates", headers=auth_headers).json()["meta"]["total"]
    assert after == before

    # 3) Create cycle
    r = client.post(
        "/api/v1/cycles",
        headers=auth_headers,
        json={
            "name": "July 2026 Nashik",
            "division": "nashik",
            "incentive_month": "2026-07",
            "candidate_version_id": cand_version,
            "hours_version_id": hours_version,
        },
    )
    assert r.status_code == 200, r.text
    cycle_id = r.json()["id"]

    # 4) Calculate
    r = client.post(f"/api/v1/cycles/{cycle_id}/calculate", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["line_count"] >= 1

    # 5) Approve + pay
    r = client.post(
        f"/api/v1/cycles/{cycle_id}/approve",
        headers=auth_headers,
        json={"comments": "ok", "pay": True},
    )
    assert r.status_code == 200, r.text

    lines = client.get(f"/api/v1/cycles/{cycle_id}/lines", headers=auth_headers).json()
    paid_line = next(l for l in lines if l["eligible"] and float(l["amount"]) > 0)
    # 6) Duplicate payment rejected
    r = client.post(
        "/api/v1/payments",
        headers=auth_headers,
        json={"incentive_line_id": paid_line["id"]},
    )
    assert r.status_code == 409, r.text
