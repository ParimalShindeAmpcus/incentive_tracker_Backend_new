"""Recruiter Master (Coordinator) presence checks for incentive calculation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.incentives.nashik_rules import normalize_person

EXEMPTED_MISSING_RECRUITER_MASTER = "EXEMPTED_MISSING_RECRUITER_MASTER"
LEGACY_MISSING_REASON = "COORDINATOR_NOT_IN_MASTER"
MISSING_RECRUITER_MASTER_REASONS = {
    EXEMPTED_MISSING_RECRUITER_MASTER,
    LEGACY_MISSING_REASON,
}
EXEMPTION_REASON_TEXT = "Hierarchy person not found in Recruiter Master"

_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "—",
    "n/a",
    "na",
    "n.a",
    "n.a.",
    "none",
    "null",
    "nil",
    "tbd",
    "unknown",
    "not applicable",
    "not available",
}


def is_blank_hierarchy_person(person: Optional[str]) -> bool:
    key = normalize_person(person)
    compact = key.replace("/", "").replace("-", "").replace(".", "")
    return key in _PLACEHOLDERS or compact in {"na", "notapplicable"}


def lookup_coordinator(coordinators: Optional[Dict[str, Any]], person: Optional[str]) -> Any:
    """Find a Recruiter Master row by normalized name/email. Status is ignored."""
    if not coordinators or is_blank_hierarchy_person(person):
        return None
    key = normalize_person(person)
    if not key:
        return None
    record = coordinators.get(key)
    if record is not None:
        return record
    for stored_key, row in coordinators.items():
        if normalize_person(str(stored_key or "")) == key:
            return row
        for attr in ("normalized_name", "full_name", "email"):
            if normalize_person(str(getattr(row, attr, None) or "")) == key:
                return row
    return None


def is_in_recruiter_master(coordinators: Optional[Dict[str, Any]], person: Optional[str]) -> bool:
    return lookup_coordinator(coordinators, person) is not None


def missing_recruiter_master_validation(lines: Any) -> Dict[str, Any]:
    """Yellow (non-blocking) cycle check: role incentives exempted because the person is absent."""
    count = sum(1 for line in (lines or []) if getattr(line, "reason", None) in MISSING_RECRUITER_MASTER_REASONS)
    return {
        "check_key": "coordinator_not_in_master",
        "severity": "YELLOW" if count else "GREEN",
        "message": "Hierarchy person not found in Recruiter Master — that role incentive is exempted",
        "count": count,
        "details_json": None,
    }
