"""Canonical Hours Template definition for Smart Match (VLOOKUP).

Single source of truth for:
- GET /vlookup/template description
- Hours Template upload column validation
"""

from __future__ import annotations

from typing import List, Sequence

# Display headers (exact order used by Hours Template download / description API).
HOURS_TEMPLATE_COLUMNS: List[str] = [
    "Candidate ID",
    "Candidate Name",
    "Client Name",
    "Hours Worked",
    "Month",
]

# Columns that must be present for upload to proceed (subset of HOURS_TEMPLATE_COLUMNS).
HOURS_TEMPLATE_REQUIRED_COLUMNS: List[str] = [
    "Candidate ID",
    "Candidate Name",
]

HOURS_TEMPLATE_UPLOAD_MESSAGE = (
    "Upload Hours Template + Consolidated File via POST /vlookup/upload"
)


def normalize_template_header(header: str) -> str:
    return str(header or "").lower().strip().replace(" ", "_")


def required_template_column_keys(
    columns: Sequence[str] = HOURS_TEMPLATE_REQUIRED_COLUMNS,
) -> set[str]:
    return {normalize_template_header(col) for col in columns}


def build_template_description_response() -> dict:
    """Payload for GET /vlookup/template — derived only from this module."""
    return {
        "columns": list(HOURS_TEMPLATE_COLUMNS),
        "message": HOURS_TEMPLATE_UPLOAD_MESSAGE,
    }
