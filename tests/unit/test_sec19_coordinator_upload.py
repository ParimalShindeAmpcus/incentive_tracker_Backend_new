"""SEC-19: Automated tests for coordinator bulk-upload file validation.

Covers:
  T1  Valid XLSX with correct columns            → 200 OK
  T2  Fake XLSX (plain text named .xlsx)         → 400
  T3  Empty file with .xlsx extension            → 400
  T4  Wrong file type (.txt)                     → 400
  T5  Corrupted XLSX (truncated ZIP)             → 400
  T6  XLSX missing required columns              → 400
  T7  File exceeding the 5 MB size limit         → 413
  T8  Zero-named file (no extension)             → 400
"""

import io
import zipfile

import openpyxl
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — build in-memory XLSX files
# ---------------------------------------------------------------------------

def _make_valid_xlsx() -> bytes:
    """Create a minimal valid coordinator XLSX with all required columns."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Coordinator Name", "Email", "Organization", "Role", "Employment Status"])
    ws.append(["Test User", "test.user@example.com", "Ampcus Inc", "Technical Recruiter", "ACTIVE"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_xlsx_missing_columns() -> bytes:
    """A real XLSX but with wrong column names."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "E-Mail", "Org"])  # wrong column names
    ws.append(["Someone", "x@y.com", "Acme"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_corrupted_xlsx() -> bytes:
    """A file with the XLSX magic bytes but a truncated/corrupt ZIP body."""
    return b"PK\x03\x04" + b"\x00" * 50  # valid magic, garbage body


def _make_oversized_xlsx(mb: int = 6) -> bytes:
    """A file larger than the 5 MB coordinator upload limit."""
    return b"PK\x03\x04" + b"\x00" * (mb * 1024 * 1024)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

UPLOAD_URL = "/api/v1/coordinators/bulk-upload"


@pytest.fixture()
def upload_headers(auth_headers: dict) -> dict:
    """Auth headers without Content-Type (multipart is set by TestClient)."""
    return auth_headers


# ---------------------------------------------------------------------------
# T1 — Valid XLSX
# ---------------------------------------------------------------------------

def test_valid_xlsx_upload_succeeds(client: TestClient, upload_headers: dict):
    """A properly structured XLSX with required columns must return 200."""
    content = _make_valid_xlsx()
    response = client.post(
        UPLOAD_URL,
        files={"file": ("coordinators.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=upload_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "created_count" in body
    assert "issues" in body
    # The row we added should be created (or result in a known validation issue, not a 500).
    assert isinstance(body["created_count"], int)


# ---------------------------------------------------------------------------
# T2 — Fake XLSX (plain text)
# ---------------------------------------------------------------------------

def test_fake_xlsx_content_returns_400(client: TestClient, upload_headers: dict):
    """A file named .xlsx but containing plain text must return 400, not 500."""
    fake_content = b"This is just plain text, not an Excel file at all."
    response = client.post(
        UPLOAD_URL,
        files={"file": ("fake.xlsx", fake_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=upload_headers,
    )
    assert response.status_code == 400, response.text
    # Response must NOT expose internal Python exception messages.
    body = response.text.lower()
    assert "zipfile" not in body
    assert "badzip" not in body
    assert "traceback" not in body
    assert "file is not a zip file" not in body


# ---------------------------------------------------------------------------
# T3 — Empty file
# ---------------------------------------------------------------------------

def test_empty_xlsx_returns_400(client: TestClient, upload_headers: dict):
    """A zero-byte file named .xlsx must return 400."""
    response = client.post(
        UPLOAD_URL,
        files={"file": ("empty.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=upload_headers,
    )
    assert response.status_code == 400, response.text


# ---------------------------------------------------------------------------
# T4 — Wrong file type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext,mime", [
    (".txt", "text/plain"),
    (".pdf", "application/pdf"),
    (".jpg", "image/jpeg"),
    (".png", "image/png"),
    (".zip", "application/zip"),
])
def test_unsupported_file_type_returns_400(client: TestClient, upload_headers: dict, ext: str, mime: str):
    """Unsupported file extensions must be rejected with 400."""
    content = b"some content"
    response = client.post(
        UPLOAD_URL,
        files={"file": (f"file{ext}", content, mime)},
        headers=upload_headers,
    )
    assert response.status_code == 400, f"Expected 400 for {ext}, got {response.status_code}: {response.text}"


# ---------------------------------------------------------------------------
# T5 — Corrupted XLSX (valid magic, truncated ZIP body)
# ---------------------------------------------------------------------------

def test_corrupted_xlsx_returns_400(client: TestClient, upload_headers: dict):
    """A file with XLSX magic bytes but corrupted ZIP body must return 400."""
    content = _make_corrupted_xlsx()
    response = client.post(
        UPLOAD_URL,
        files={"file": ("corrupted.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=upload_headers,
    )
    assert response.status_code == 400, response.text
    body = response.text.lower()
    assert "traceback" not in body
    assert "zipfile" not in body


# ---------------------------------------------------------------------------
# T6 — XLSX with missing required columns
# ---------------------------------------------------------------------------

def test_xlsx_missing_columns_returns_400(client: TestClient, upload_headers: dict):
    """A valid XLSX but with wrong/missing required columns must return 400."""
    content = _make_xlsx_missing_columns()
    response = client.post(
        UPLOAD_URL,
        files={"file": ("wrong_columns.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=upload_headers,
    )
    assert response.status_code == 400, response.text
    assert "column" in response.text.lower()


# ---------------------------------------------------------------------------
# T7 — Oversized file
# ---------------------------------------------------------------------------

def test_oversized_file_returns_413(client: TestClient, upload_headers: dict):
    """A file larger than the 5 MB limit must return 413."""
    content = _make_oversized_xlsx(mb=6)
    response = client.post(
        UPLOAD_URL,
        files={"file": ("huge.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=upload_headers,
    )
    assert response.status_code == 413, response.text


# ---------------------------------------------------------------------------
# T8 — No file extension
# ---------------------------------------------------------------------------

def test_no_extension_returns_400(client: TestClient, upload_headers: dict):
    """A filename with no extension must be rejected."""
    response = client.post(
        UPLOAD_URL,
        files={"file": ("noextension", b"anything", "application/octet-stream")},
        headers=upload_headers,
    )
    assert response.status_code == 400, response.text


# ---------------------------------------------------------------------------
# Regression: unauthenticated upload is still blocked
# ---------------------------------------------------------------------------

def test_unauthenticated_upload_returns_401(client: TestClient):
    """Without auth the endpoint must still return 401."""
    content = _make_valid_xlsx()
    response = client.post(
        UPLOAD_URL,
        files={"file": ("coordinators.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 401, response.text
