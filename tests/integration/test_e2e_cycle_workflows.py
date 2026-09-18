"""End-to-End (E2E) Cycle Lifecycle Workflow Integration Test Suite.

Tests complete business flows:
1. Cycle Creation -> Candidate/Data ingest -> Calculation -> Checklist -> Adjustments -> Approval -> Export -> Locked State
2. Ampcus Tech In-House E2E Flow
3. Nashik Division Hours-Upload & Calculation E2E Flow
4. Ampcus Tech Client Payment Realization & Calculation E2E Flow
5. Hours Benchmarks and Reconciliation Reports
"""

import io
import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from openpyxl import Workbook


class TestInhouseCycleE2ELifecycle:
    """Full lifecycle workflow for Ampcus Tech In-House cycle."""

    def test_complete_inhouse_cycle_lifecycle(self, client: TestClient, auth_headers: dict):
        # 1. Ingest In-House Candidate FIRST so it exists in Candidate Master
        version_res = client.post(
            "/api/v1/candidate-data/versions",
            json={
                "version_label": "v1.0-inhouse-test",
                "source_filename": "inhouse_test.xlsx",
                "division": "ampcusTechInhouse",
                "rows": [
                    {
                        "candidate_name": "Inhouse Senior Placement",
                        "start_id": "INH-001",
                        "external_candidate_id": "INH-001",
                        "start_date": "2026-04-01",
                        "job_level": "Above Manager Level",
                        "organization": "Ampcus Tech Inhouse",
                        "division": "ampcusTechInhouse",
                        "recruiter": "Inhouse Recruiter",
                        "manager": "Inhouse Manager",
                        "center_head": "Inhouse Center Head",
                        "status": "ACTIVE",
                    }
                ],

            },
            headers=auth_headers,
        )
        assert version_res.status_code == 200, version_res.text

        # 2. Create Cycle
        create_res = client.post(
            "/api/v1/cycles",
            json={
                "incentive_month": "2026-08",
                "division": "ampcusTechInhouse",
                "name": "E2E In-House August 2026",
            },
            headers=auth_headers,
        )
        assert create_res.status_code == 200
        cycle = create_res.json()
        cycle_id = cycle["id"]
        assert cycle["status"].upper() in ("DRAFT", "CREATED")


        # 3. Calculate Cycle
        calc_res = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert calc_res.status_code == 200, calc_res.text
        calc_data = calc_res.json()
        assert "status" in calc_data or "lines" in calc_data

        # 4. View Checklist Items
        checklist_res = client.get(f"/api/v1/cycles/{cycle_id}/checklist", headers=auth_headers)
        assert checklist_res.status_code == 200
        checklist = checklist_res.json()
        if checklist:
            item_id = checklist[0]["id"]
            # Complete checklist item
            patch_item_res = client.patch(
                f"/api/v1/cycles/{cycle_id}/checklist/{item_id}",
                json={"is_checked": True, "notes": "Verified by QA tester"},
                headers=auth_headers,
            )
            assert patch_item_res.status_code == 200
            assert patch_item_res.json()["is_checked"] is True

        # 5. Check Summary and Incentive Lines
        summary_res = client.get(f"/api/v1/cycles/{cycle_id}/summary", headers=auth_headers)
        assert summary_res.status_code == 200

        lines_res = client.get(f"/api/v1/cycles/{cycle_id}/lines", headers=auth_headers)
        assert lines_res.status_code == 200
        lines = lines_res.json()
        assert isinstance(lines, list)

        # 6. Add Manual Adjustment
        adj_res = client.post(
            f"/api/v1/cycles/{cycle_id}/adjustments",
            json={
                "candidate_id": lines[0]["candidate_id"] if lines else None,
                "candidate_name": "Inhouse Senior Placement",
                "kind": "BONUS",
                "person": "Inhouse Recruiter",
                "amount": 500.0,
                "notes": "Exceptional milestone bonus",
            },
            headers=auth_headers,
        )
        assert adj_res.status_code == 200
        assert float(adj_res.json()["amount"]) == 500.0

        # Verify adjustment is listed
        list_adj_res = client.get(f"/api/v1/cycles/{cycle_id}/adjustments", headers=auth_headers)
        assert list_adj_res.status_code == 200
        assert len(list_adj_res.json()) >= 1

        # 7. Approve and Finalize Cycle
        approve_res = client.post(
            f"/api/v1/cycles/{cycle_id}/approve",
            json={"comments": "Approved for disbursement by Finance"},
            headers=auth_headers,
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"].upper() == "APPROVED"

        # 8. Check Approval Results Audit Log
        results_res = client.get(f"/api/v1/cycles/{cycle_id}/approval-results", headers=auth_headers)
        assert results_res.status_code == 200
        assert len(results_res.json()) >= 1
        assert results_res.json()[-1]["cycle_status"].upper() == "APPROVED"

        # 9. Download / Export Approved Cycle Payout Report
        export_res = client.get(f"/api/v1/cycles/{cycle_id}/export", headers=auth_headers)
        assert export_res.status_code == 200
        assert (
            "spreadsheetml" in export_res.headers.get("content-type", "")
            or "octet-stream" in export_res.headers.get("content-type", "")
            or export_res.headers.get("content-disposition")
        )

        # 10. Verify Locked Invariant: cannot recalculate approved cycle
        recalc_attempt = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert recalc_attempt.status_code == 400


class TestNashikHoursUploadAndCalculationE2E:
    """E2E workflow for Nashik cycle with Hours Excel generation & upload."""

    def test_nashik_hours_upload_and_calculation(self, client: TestClient, auth_headers: dict):
        # 1. Ingest candidate for Nashik FIRST so it exists in Candidate Master
        cand_res = client.post(
            "/api/v1/candidate-data/versions",
            json={
                "version_label": "v1.0-nashik-e2e",
                "source_filename": "nashik_e2e.xlsx",
                "division": "nashik",
                "rows": [
                    {
                        "candidate_name": "Nashik Consultant 1",
                        "start_id": "NSK-001",
                        "external_candidate_id": "NSK-001",
                        "start_date": "2026-01-01",
                        "margin": 8.50,
                        "organization": "Ampcus Inc",
                        "division": "nashik",
                        "recruiter": "Nashik Recruiter",
                        "team_lead": "Nashik TL",
                        "manager": "Nashik Manager",
                        "recruiter_location": "Nashik",
                        "status": "ACTIVE",
                    }
                ],
            },
            headers=auth_headers,
        )
        assert cand_res.status_code == 200, cand_res.text

        # 2. Create Nashik cycle
        cycle_res = client.post(
            "/api/v1/cycles",
            json={
                "incentive_month": "2026-08",
                "division": "nashik",
                "name": "Nashik August 2026 E2E",
            },
            headers=auth_headers,
        )
        assert cycle_res.status_code == 200
        cycle_id = cycle_res.json()["id"]

        # 3. Build in-memory Hours Excel file
        wb = Workbook()
        ws = wb.active
        ws.title = "Hours"
        ws.append(["Candidate ID", "Candidate Name", "Month", "Hours Worked", "Status"])
        ws.append(["NSK-001", "Nashik Consultant 1", "2026-08", 160, "Active"])

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)

        # 4. Upload hours file
        upload_res = client.post(
            f"/api/v1/cycles/{cycle_id}/hours-upload",
            files={"file": ("hours_august_2026.xlsx", excel_buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )
        assert upload_res.status_code == 200, upload_res.text
        upload_data = upload_res.json()
        assert upload_data["matched_count"] >= 1


        # 5. Calculate Cycle
        calc_res = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert calc_res.status_code == 200, calc_res.text

        # 6. Verify Lines & Validations
        val_res = client.get(f"/api/v1/cycles/{cycle_id}/validations", headers=auth_headers)
        assert val_res.status_code == 200

        lines_res = client.get(f"/api/v1/cycles/{cycle_id}/lines", headers=auth_headers)
        assert lines_res.status_code == 200
        lines = lines_res.json()
        assert len(lines) > 0


class TestBenchmarksAndReportsEndpoints:
    """Validate auxiliary system endpoints for hours benchmarks and reports."""

    def test_hours_benchmarks_retrieval(self, client: TestClient, auth_headers: dict):
        """Verify hours benchmarks are available for all divisions (requires auth after F30 fix)."""
        res = client.get("/api/v1/hours-benchmarks", headers=auth_headers)
        assert res.status_code == 200
        benchmarks = res.json()
        assert isinstance(benchmarks, list)
        divisions = {b["division"] for b in benchmarks}
        assert "nashik" in divisions

    def test_root_endpoint_metadata(self, client: TestClient):
        """Verify root endpoint responds with ok status."""
        res = client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
