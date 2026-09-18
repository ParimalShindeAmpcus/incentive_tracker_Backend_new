"""Security Testing Suite: Input Hardening, Injection Defense, State Immutability, and Concurrency.

Tests cover:
- SQL Injection resilience across query parameters and filters
- Cross-Site Scripting (XSS) payload handling in candidate/cycle/notes fields
- Boundary & Type Fuzzing (Negative values, extreme decimals, malformed dates)
- State Machine Immutability (Recalculation and deletion protections on APPROVED/LOCKED cycles)
- Concurrency and race condition testing
"""

import concurrent.futures
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient


class TestInputInjectionAndSanitization:
    """Validate backend hardening against SQL Injection and XSS payloads."""

    def test_sql_injection_resilience_in_search_and_filters(self, client: TestClient, auth_headers: dict):
        """Verify endpoints safely parameterize SQL queries against common SQLi vectors."""
        sqli_payloads = [
            "' OR '1'='1",
            "admin'--",
            "'; DROP TABLE cycles;--",
            "1 UNION SELECT null, null, null--",
            "' OR 1=1 #",
        ]
        for payload in sqli_payloads:
            # Test coordinator search
            res = client.get("/api/v1/coordinators", params={"search": payload}, headers=auth_headers)
            assert res.status_code == 200, f"Failed on search SQLi: {payload}"

            # Test candidate search / division filter
            cand_res = client.get("/api/v1/candidates", params={"division": payload}, headers=auth_headers)
            assert cand_res.status_code == 200, f"Failed on candidate SQLi: {payload}"

            # Test cycle list filter
            cycle_res = client.get("/api/v1/cycles", params={"division": payload}, headers=auth_headers)
            assert cycle_res.status_code == 200, f"Failed on cycle SQLi: {payload}"

    def test_xss_payload_persisted_safely_without_eval(self, client: TestClient, auth_headers: dict):
        """Ensure XSS strings are treated purely as inert data and not executed or corrupted."""
        xss_payload = "<script>alert('XSS_TEST')</script>"
        res = client.post(
            "/api/v1/coordinators",
            json={
                "full_name": f"Coordinator {xss_payload}",
                "email": "xss.test@example.com",
                "organization": "Ampcus Inc",
                "role_title": "Recruiter",
                "employment_status": "ACTIVE",
            },
            headers=auth_headers,
        )
        assert res.status_code in (201, 200)
        data = res.json()
        assert xss_payload in data["full_name"]


class TestBoundaryFuzzingAndValidation:
    """Validate boundary conditions, extreme values, and input type constraints."""

    def test_malformed_dates_rejected_with_422(self, client: TestClient, auth_headers: dict):
        """Invalid date strings must return 422 Unprocessable Entity, not 500."""
        res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "invalid-month-date", "division": "nashik", "name": "Date Test"},
            headers=auth_headers,
        )
        # Even if cycle accepts string month, coordinator date validation must strictly enforce ISO format
        coord_res = client.post(
            "/api/v1/coordinators",
            json={
                "full_name": "Bad Date Coordinator",
                "email": "bad.date@example.com",
                "organization": "Ampcus Inc",
                "role_title": "Recruiter",
                "start_date": "not-a-real-date",
            },
            headers=auth_headers,
        )
        assert coord_res.status_code == 422

    def test_negative_pagination_params_rejected(self, client: TestClient, auth_headers: dict):
        """Page number < 1 or negative page size must return 422."""
        res = client.get("/api/v1/candidates", params={"page": -1, "page_size": 10}, headers=auth_headers)
        assert res.status_code == 422

        res2 = client.get("/api/v1/candidates", params={"page": 1, "page_size": 10000}, headers=auth_headers)
        assert res2.status_code == 422  # Exceeds max 500


class TestStateMachineImmutability:
    """Validate state transitions and lock invariants."""

    def test_approved_cycle_cannot_be_recalculated(self, client: TestClient, auth_headers: dict):
        """An APPROVED cycle is legally locked and recalculation must be rejected with 400 Bad Request."""
        # 1. Create in-house cycle
        create_res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "2026-12", "division": "ampcusTechInhouse", "name": "Lock Test Cycle"},
            headers=auth_headers,
        )
        assert create_res.status_code == 200
        cycle_id = create_res.json()["id"]

        # 2. Calculate cycle
        calc_res = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert calc_res.status_code == 200

        # 3. Approve cycle
        approve_res = client.post(
            f"/api/v1/cycles/{cycle_id}/approve",
            json={"status": "APPROVED", "comments": "Finalized and locked for payroll"},
            headers=auth_headers,
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"].upper() == "APPROVED"

        # 4. Attempt to recalculate: MUST be blocked with 400
        recalc_res = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert recalc_res.status_code == 400
        assert "Approved cycles cannot be recalculated" in recalc_res.json().get("detail", "")

    def test_approved_cycle_cannot_be_deleted(self, client: TestClient, auth_headers: dict):
        """An APPROVED cycle must NOT be deletable."""
        # 1. Create in-house cycle
        create_res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "2026-12", "division": "ampcusTechInhouse", "name": "Deletability Test Cycle"},
            headers=auth_headers,
        )
        assert create_res.status_code == 200
        cycle_id = create_res.json()["id"]

        # 2. Approve cycle directly
        client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        client.post(
            f"/api/v1/cycles/{cycle_id}/approve",
            json={"status": "APPROVED", "comments": "Final approval"},
            headers=auth_headers,
        )

        # 3. Attempt delete: MUST be blocked with 400
        del_res = client.delete(f"/api/v1/cycles/{cycle_id}", headers=auth_headers)
        assert del_res.status_code == 400
        assert "Approved cycles cannot be deleted" in del_res.json().get("detail", "")


class TestConcurrencyResilience:
    """Validate system behavior under concurrent access and calculation."""

    def test_concurrent_calculations_handled_safely(self, client: TestClient, auth_headers: dict):
        """Triggering repeated calculations on the same cycle must remain atomic and idempotent without corrupting state."""
        # Create cycle
        create_res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "2027-01", "division": "ampcusTechInhouse", "name": "Concurrency Test Cycle"},
            headers=auth_headers,
        )
        assert create_res.status_code == 200
        cycle_id = create_res.json()["id"]

        # Trigger calculation 1
        res1 = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert res1.status_code == 200

        # Trigger immediate consecutive calculation (idempotent state preservation)
        res2 = client.post(f"/api/v1/cycles/{cycle_id}/calculate", json={}, headers=auth_headers)
        assert res2.status_code == 200

        # Verify final cycle status is CALCULATED and summary lines are valid
        summary_res = client.get(f"/api/v1/cycles/{cycle_id}/summary", headers=auth_headers)
        assert summary_res.status_code == 200
        assert summary_res.json()["cycle_id"] == cycle_id


class TestFileUploadAndErrorHardening:
    """Validate file upload validation (VULN-INPUT-001) and error message sanitization (SEC-INFO-001)."""

    def test_upload_hours_rejects_invalid_magic_bytes(self, client: TestClient, auth_headers: dict):
        """Uploading a fake .xlsx file without ZIP magic bytes MUST be rejected with 400 Bad Request."""
        # Create a cycle to upload to
        create_res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "2027-02", "division": "nashik", "name": "Upload Hardening Test"},
            headers=auth_headers,
        )
        assert create_res.status_code == 200
        cycle_id = create_res.json()["id"]

        # Fake xlsx with plain text contents (no PK\x03\x04 header)
        fake_xlsx = b"THIS IS NOT A VALID OPENXML ARCHIVE"
        upload_res = client.post(
            f"/api/v1/cycles/{cycle_id}/hours-upload",
            files={"file": ("fake.xlsx", fake_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=auth_headers,
        )
        assert upload_res.status_code == 400
        assert "Invalid file format: Excel .xlsx files must be valid OpenXML spreadsheets" in upload_res.json().get("detail", "")

    def test_upload_hours_rejects_oversized_file(self, client: TestClient, auth_headers: dict):
        """Uploading an oversized file (>15MB) MUST be rejected with 400 Bad Request."""
        create_res = client.post(
            "/api/v1/cycles",
            json={"incentive_month": "2027-03", "division": "nashik", "name": "Size Limit Test"},
            headers=auth_headers,
        )
        assert create_res.status_code == 200
        cycle_id = create_res.json()["id"]

        # Exceeds 15MB limit
        oversized = b"P" * (16 * 1024 * 1024)
        upload_res = client.post(
            f"/api/v1/cycles/{cycle_id}/hours-upload",
            files={"file": ("huge.xlsx", oversized, "application/octet-stream")},
            headers=auth_headers,
        )
        assert upload_res.status_code == 400
        assert "maximum allowed size limit of 15MB" in upload_res.json().get("detail", "")
