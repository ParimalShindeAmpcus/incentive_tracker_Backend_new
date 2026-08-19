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


def is_ampcus_inhouse_division(division: Optional[str]) -> bool:
    normalized = str(division or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    return "inhouse" in normalized or normalized in {"ampcustechinhouse", "ampcusinhouse"}


def _line(c: Candidate, role: str, person: Optional[str], amount: int, eligible: bool, reason: str) -> LineDraft:
    return LineDraft(c.id, c.candidate_name, role, (person or "—").strip(), "INHOUSE", "Ampcus Tech In-House 90-day rule", eligible, Decimal(amount), Decimal("1") if eligible else ZERO, Decimal(amount) if eligible else ZERO, ZERO, None, reason, [json.dumps({"placement_level": c.placement_level, "start_date": str(c.start_date) if c.start_date else None})])


def calculate_placement(c: Candidate, *, cycle_end: date, coordinators: Dict[str, CoordinatorRecord], paid_keys: Optional[set[str]] = None) -> List[LineDraft]:
    people = {"Recruiter": c.recruiter, "Manager": c.manager, "Center Head": c.center_head or c.avp}
    status = str(c.status or "").upper()
    days = (cycle_end - c.start_date).days if c.start_date else 0
    if not c.start_date or c.start_date < MIN_START or days < 90:
        return [_line(c, role, person, 0, False, "INHOUSE_90_DAY_REQUIREMENT_NOT_MET") for role, person in people.items()]
    if c.incentive_active is False or any(x in status for x in ("INACTIVE", "TERMINAT", "RESIGN", "LEFT")):
        return [_line(c, role, person, 0, False, "CANDIDATE_INACTIVE") for role, person in people.items()]
    if any(not person for person in people.values()):
        return [_line(c, role, person, 0, False, "MISSING_HIERARCHY") for role, person in people.items()]
    recruiter_amount = 5000 if str(c.placement_level or "").upper() == "ABOVE_MANAGER" else 3000
    amounts = {"Recruiter": recruiter_amount, "Manager": 500, "Center Head": 1000}
    lines: List[LineDraft] = []
    for role, person in people.items():
        person_clean = (person or "").strip().lower()
        key = f"{c.id}|INHOUSE|{role}|{person_clean}"
        if paid_keys and key in paid_keys:
            lines.append(_line(c, role, person, 0, False, "ALREADY_PAID"))
            continue
        record = coordinators.get(person_clean)
        coordinator_status = getattr(getattr(record, "employment_status", None), "value", getattr(record, "employment_status", "ACTIVE"))
        if role == "Recruiter" and str(coordinator_status).upper() in {"LEFT", "NOTICE"}:
            lines.append(_line(c, role, person, 0, False, "COORDINATOR_LEFT" if str(coordinator_status).upper() == "LEFT" else "COORDINATOR_ON_NOTICE"))
        else:
            lines.append(_line(c, role, person, amounts[role], True, "ELIGIBLE"))
    return lines
