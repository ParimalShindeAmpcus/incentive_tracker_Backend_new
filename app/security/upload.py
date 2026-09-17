"""SEC-19: Centralised upload-file validation utilities.

Provides lightweight, reusable guards for all file-upload endpoints:

* Extension allow-list enforcement
* Empty-file rejection
* Magic-bytes / content-type validation (XLSX = ZIP magic, CSV = text)
* Maximum size enforcement (enforced *before* the caller reads the body)

All rejections raise ``fastapi.HTTPException`` with 400/413 status codes and
safe, generic messages — no internal library errors or stack traces are leaked.
"""

import io
import zipfile
from typing import Collection

from fastapi import HTTPException, UploadFile, status

# XLSX files are ZIP archives; the first 4 bytes are the PK magic.
_XLSX_MAGIC = b"PK\x03\x04"
# Older legacy XLS (BIFF) magic — we don't claim to support it, but note it.
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"

# Allowed extensions for coordinator bulk upload (lowercase, with dot).
COORDINATOR_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".csv"})

# Maximum upload size for coordinator bulk files (5 MB is generous for a
# coordinator list; the existing app-wide dep uses 25 MB but that is too
# permissive for a simple name/email list).
COORDINATOR_MAX_MB: int = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extension(filename: str) -> str:
    """Return the normalised lowercase extension including the leading dot."""
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read up to *max_bytes* from the upload, then seek back to 0.

    Raises HTTP 413 if the content exceeds *max_bytes*.
    Raises HTTP 400 if the file is empty (zero bytes).
    """
    file.file.seek(0)
    data = file.file.read(max_bytes + 1)
    file.file.seek(0)

    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(data) > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {max_mb} MB.",
        )
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_coordinator_upload(file: UploadFile) -> bytes:
    """Validate and return the full file content for a coordinator bulk upload.

    Checks (in order):
    1. Filename / extension is present and in the allow-list.
    2. File is not empty and does not exceed COORDINATOR_MAX_MB.
    3. For XLSX: magic bytes confirm a real ZIP/XLSX container.
    4. For XLSX: the ZIP can actually be opened (not just named .xlsx).
    5. For CSV: content can be decoded as UTF-8 or latin-1.

    Returns:
        The raw ``bytes`` of the file, ready to be passed to the service layer.

    Raises:
        HTTPException(400) — invalid extension, empty file, bad content.
        HTTPException(413) — file exceeds the size limit.
    """
    filename: str = (file.filename or "").strip()
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided.",
        )

    ext = _extension(filename)
    if ext not in COORDINATOR_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(COORDINATOR_UPLOAD_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {allowed}.",
        )

    max_bytes = COORDINATOR_MAX_MB * 1024 * 1024
    content = _read_limited(file, max_bytes)

    if ext == ".xlsx":
        _validate_xlsx_bytes(content)
    elif ext == ".csv":
        _validate_csv_bytes(content)

    return content


def _validate_xlsx_bytes(content: bytes) -> None:
    """Verify that *content* is a genuine XLSX (ZIP) workbook.

    Raises HTTP 400 with a safe message if validation fails.
    """
    # 1. Check magic bytes (PK signature of a ZIP archive).
    if not content[:4] == _XLSX_MAGIC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Excel file. The file does not appear to be a valid XLSX workbook.",
        )

    # 2. Attempt to open the ZIP container to catch truncated / corrupted ZIPs.
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # A valid XLSX must contain the Office Open XML content-type part.
            names = zf.namelist()
            if "[Content_Types].xml" not in names:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Excel file. The uploaded file is not a valid XLSX workbook.",
                )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Excel file. The uploaded file could not be read as an XLSX workbook.",
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Excel file. The uploaded file could not be processed.",
        )


def _validate_csv_bytes(content: bytes) -> None:
    """Verify that *content* can be decoded as text (CSV).

    Raises HTTP 400 with a safe message if validation fails.
    """
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid CSV file. The file could not be decoded as text.",
            )
