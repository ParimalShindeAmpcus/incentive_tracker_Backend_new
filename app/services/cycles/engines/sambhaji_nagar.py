"""Sambhaji Nagar margin x hours engine; payment is required below 160h."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from app.repositories.entities.candidate import Candidate
from app.repositories.entities.coordinator import CoordinatorRecord
from app.services.incentives.nashik_calculator import LineDraft

ZERO = Decimal("0")
BANDS: Tuple[Tuple[Decimal, Decimal, Tuple[int, int, int, int, int]], ...] = (
    (Decimal("1"), Decimal("3"), (500, 1000, 2000, 3000, 4000)), (Decimal("3.01"), Decimal("5"), (1000, 2000, 3000, 4000, 5000)),
    (Decimal("5.01"), Decimal("7"), (2000, 3000, 4000, 5000, 7000)), (Decimal("7.01"), Decimal("10"), (3000, 4000, 5000, 6000, 8500)),
    (Decimal("10.01"), Decimal("15"), (4000, 5000, 6000, 7000, 10000)), (Decimal("15.01"), Decimal("20"), (5000, 6000, 7000, 8000, 15000)),
    (Decimal("20.01"), Decimal("30"), (6000, 7000, 8000, 10000, 20000)), (Decimal("30.01"), Decimal("50"), (7000, 8000, 9000, 12000, 25000)),
)
FIXED = {"Team Lead": 500, "Manager": 1000, "Senior Manager": 1500, "CRM": 1000, "Associate Director": 1750, "Center Head": 1750}

def is_sambhaji_nagar_division(division: Optional[str]) -> bool:
    return str(division or "").strip().lower().replace(" ", "").replace("-", "") in {"sambhajinagar", "sambhajinagardivision"}

def matrix_amount(margin: Optional[Decimal], hours: Decimal) -> int:
    if margin is None or hours < 0: return 0
    index = 0 if hours <= 40 else 1 if hours <= 80 else 2 if hours <= 120 else 3 if hours <= 160 else 4
    for low, high, values in BANDS:
        if low <= margin <= high: return values[index]
    return 0

def _line(c: Candidate, role: str, person: Optional[str], amount: int, hours: Decimal, eligible: bool, reason: str, kind="RECURRING") -> LineDraft:
    return LineDraft(c.id, c.candidate_name, role, (person or "—").strip(), kind, "Sambhaji Nagar margin x hours", eligible, Decimal(amount), Decimal("1") if eligible else ZERO, Decimal(amount) if eligible else ZERO, hours, c.margin, reason, [json.dumps({"margin": str(c.margin), "hours": str(hours)})])

def calculate_placement(c: Candidate, *, hours: Decimal, payment_status: str, coordinators: Dict[str, CoordinatorRecord]) -> List[LineDraft]:
    paid = payment_status.upper() in {"RECEIVED", "PAYMENT_RECEIVED", "NOT_APPLICABLE"}
    requires_payment = hours < Decimal("160")
    recruiter_status = getattr(coordinators.get((c.recruiter or "").strip().lower()), "employment_status", "ACTIVE")
    recruiter_status = getattr(recruiter_status, "value", str(recruiter_status)).upper()
    amount = matrix_amount(c.margin, hours)
    blocked = "PAYMENT_PENDING" if requires_payment and not paid else "MARGIN_OR_HOURS_OUTSIDE_MATRIX" if not amount else ""
    recruiter_ok = bool(c.recruiter) and recruiter_status not in {"LEFT", "NOTICE"} and not blocked
    lines = [_line(c, "Recruiter", c.recruiter, amount, hours, recruiter_ok, "COORDINATOR_LEFT" if recruiter_status == "LEFT" else "COORDINATOR_ON_NOTICE" if recruiter_status == "NOTICE" else blocked or "ELIGIBLE")]
    for role, person in {"Team Lead": c.team_lead, "Manager": c.manager, "Senior Manager": c.senior_manager, "CRM": c.crm, "Associate Director": c.associate_director, "Center Head": c.center_head}.items():
        if person:
            lines.append(_line(c, role, person, FIXED[role], hours, not blocked, blocked or "ELIGIBLE", "ONE_TIME"))
    return lines

def special_average(lines: Sequence[LineDraft]) -> List[LineDraft]:
    groups: Dict[str, List[LineDraft]] = {}
    for line in lines:
        if line.role == "Recruiter" and line.eligible and line.hours >= Decimal("160"):
            groups.setdefault(line.person.lower(), []).append(line)
    extras = []
    for items in groups.values():
        if len(items) >= 2:
            avg = sum((item.amount for item in items), ZERO) / Decimal(len(items))
            first = items[0]
            extras.append(LineDraft(first.candidate_id, f"{len(items)} placements ({first.person})", "Recruiter", first.person, "SPECIAL", "Sambhaji Nagar multiple-placement average", True, avg, Decimal("1"), avg, ZERO, first.margin, "Eligible recruiter multiple-placement average", ["Average of 160+ hour placements"] ))
    return list(lines) + extras
