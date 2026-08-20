"""Ampcus Tech In-House 90-day incentive engine."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.repositories.entities.candidate import Candidate
from app.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from app.services.incentives.nashik_calculator import LineDraft

ZERO = Decimal("0")
MIN_START = date(2025, 7, 1)
MAX_ROLES_PER_PERSON = 2


def is_ampcus_inhouse_division(division: Optional[str]) -> bool:
    normalized = str(division or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    return "inhouse" in normalized or normalized in {"ampcustechinhouse", "ampcusinhouse"}


def _line(c: Candidate, role: str, person: Optional[str], amount: int, eligible: bool, reason: str) -> LineDraft:
    return LineDraft(c.id, c.candidate_name, role, (person or "—").strip(), "INHOUSE", "Ampcus Tech In-House 90-day rule", eligible, Decimal(amount), Decimal("1") if eligible else ZERO, Decimal(amount) if eligible else ZERO, ZERO, None, reason, [json.dumps({"placement_level": c.placement_level, "start_date": str(c.start_date) if c.start_date else None})])


def _limit_roles_inhouse(people: Dict[str, Optional[str]], amounts: Dict[str, int]) -> Dict[str, Optional[str]]:
    """Apply max-two-roles rule: if one person holds multiple roles, keep only
    the top 2 highest-payout roles for that person."""
    by_person: Dict[str, List[str]] = {}
    for role, person in people.items():
        if person and person.strip():
            key = person.strip().lower()
            by_person.setdefault(key, []).append(role)

    excluded_roles: set[str] = set()
    for person_key, roles in by_person.items():
        if len(roles) <= MAX_ROLES_PER_PERSON:
            continue
        # Sort by payout descending, keep top 2
        sorted_roles = sorted(roles, key=lambda r: amounts.get(r, 0), reverse=True)
        for excess_role in sorted_roles[MAX_ROLES_PER_PERSON:]:
            excluded_roles.add(excess_role)
    return excluded_roles


def calculate_placement(c: Candidate, *, cycle_end: date, coordinators: Dict[str, CoordinatorRecord], paid_keys: Optional[set[str]] = None) -> List[LineDraft]:
    people = {"Recruiter": c.recruiter, "Manager": c.manager, "Center Head": c.center_head or c.avp}
    status = str(c.status or "").upper()
    days = (cycle_end - c.start_date).days if c.start_date else 0

    # --- Candidate-level gates (all roles excluded together) ---
    if not c.start_date or c.start_date < MIN_START or days < 90:
        return [_line(c, role, person, 0, False, "INHOUSE_90_DAY_REQUIREMENT_NOT_MET") for role, person in people.items()]
    # W2: Added ABSCOND to catch absconded candidates
    if c.incentive_active is False or any(x in status for x in ("INACTIVE", "TERMINAT", "RESIGN", "LEFT", "ABSCOND")):
        return [_line(c, role, person, 0, False, "CANDIDATE_INACTIVE") for role, person in people.items()]

    recruiter_amount = 5000 if str(c.placement_level or "").upper() == "ABOVE_MANAGER" else 3000
    amounts = {"Recruiter": recruiter_amount, "Manager": 500, "Center Head": 1000}

    # W1: Max-two-roles — if one person holds 3+ roles, exclude lowest-payout extras
    excluded_roles = _limit_roles_inhouse(people, amounts)

    lines: List[LineDraft] = []
    for role, person in people.items():
        # C2: Per-role hierarchy check — only exclude the specific missing role
        if not person or not person.strip():
            lines.append(_line(c, role, person, 0, False, "MISSING_HIERARCHY"))
            continue

        # W1: Max-two-roles enforcement
        if role in excluded_roles:
            lines.append(_line(c, role, person, 0, False, "EXCEEDED_MAX_ROLES"))
            continue

        person_clean = person.strip().lower()

        # Deduplication check
        key = f"{c.id}|INHOUSE|{role}|{person_clean}"
        if paid_keys and key in paid_keys:
            lines.append(_line(c, role, person, 0, False, "ALREADY_PAID"))
            continue

        # W3: Check if coordinator exists in master
        record = coordinators.get(person_clean)
        if not record:
            lines.append(_line(c, role, person, 0, False, "COORDINATOR_NOT_IN_MASTER"))
            continue

        # C1: Coordinator status check for ALL roles (not just Recruiter)
        coordinator_status = getattr(getattr(record, "employment_status", None), "value", getattr(record, "employment_status", "ACTIVE"))
        if str(coordinator_status).upper() in {"LEFT", "NOTICE"}:
            reason = "COORDINATOR_LEFT" if str(coordinator_status).upper() == "LEFT" else "COORDINATOR_ON_NOTICE"
            lines.append(_line(c, role, person, 0, False, reason))
        else:
            lines.append(_line(c, role, person, amounts[role], True, "ELIGIBLE"))
    return lines

