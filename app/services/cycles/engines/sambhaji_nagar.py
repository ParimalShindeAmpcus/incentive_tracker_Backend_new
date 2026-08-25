"""Sambhaji Nagar margin x hours engine.

Strict rules per Incentive Calculation Process document:
 - Applicable organisations: Bravens, Ampcus Inc., ITech
 - Applicable location: Sambhaji Nagar (recruiter_location)
 - Full-Time (FULLTIME) placements are excluded
 - For < 160 hours: ALL roles (Recruiter + Leadership) incentive released ONLY after client payment received
 - For 160+ hours: no payment gate
 - Recruiter Special Incentive: only for recruiters with 2+ placements >=160 hrs in same month
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from app.repositories.entities.candidate import Candidate
from app.repositories.entities.coordinator import CoordinatorRecord
from app.services.cycles.recruiter_master import (
    EXEMPTED_MISSING_RECRUITER_MASTER,
    EXEMPTION_REASON_TEXT,
    lookup_coordinator,
)
from app.services.incentives.nashik_calculator import LineDraft

ZERO = Decimal("0")

# TABLE 5 - Sambhaji Nagar Incentive Matrix (Recruiter, per placement)
# (margin_low, margin_high, (0-40h, 41-80h, 81-120h, 121-160h, 161+h))
BANDS: Tuple[Tuple[Decimal, Decimal, Tuple[int, int, int, int, int]], ...] = (
    (Decimal("1.00"),  Decimal("3.00"),  (500,  1000, 2000, 3000, 4000)),
    (Decimal("3.01"),  Decimal("5.00"),  (1000, 2000, 3000, 4000, 5000)),
    (Decimal("5.01"),  Decimal("7.00"),  (2000, 3000, 4000, 5000, 7000)),
    (Decimal("7.01"),  Decimal("10.00"), (3000, 4000, 5000, 6000, 8500)),
    (Decimal("10.01"), Decimal("15.00"), (4000, 5000, 6000, 7000, 10000)),
    (Decimal("15.01"), Decimal("20.00"), (5000, 6000, 7000, 8000, 15000)),
    (Decimal("20.01"), Decimal("30.00"), (6000, 7000, 8000, 10000, 20000)),
    (Decimal("30.01"), Decimal("50.00"), (7000, 8000, 9000, 12000, 25000)),
)

# TABLE 6 - ONE_TIME fixed incentives for leadership roles
FIXED: Dict[str, int] = {
    "Team Lead":           500,
    "Manager":            1000,
    "Senior Manager":     1500,
    "CRM":                1000,
    "Associate Director": 1750,
    "Center Head":        1750,
}

VALID_ORGS = {"bravens", "ampcus inc", "ampcus inc.", "itech"}

# Valid Sambhaji Nagar location keywords
VALID_LOCATIONS = {"sambhaji nagar", "sambhajinagar", "sambhaji"}


def is_sambhaji_nagar_division(division: Optional[str]) -> bool:
    norm = str(division or "").strip().lower().replace(" ", "").replace("-", "")
    return norm in {"sambhajinagar", "sambhajinagardivision"}


def is_valid_sn_location(recruiter_location: Optional[str]) -> bool:
    loc = str(recruiter_location or "").strip().lower()
    return any(kw in loc for kw in VALID_LOCATIONS)


def _limit_roles_sambhaji(people: Dict[str, Optional[str]], amounts: Dict[str, int]) -> set[str]:
    """Apply max-two-roles rule: if one person holds multiple roles, keep only
    the top 2 highest-payout roles for that person."""
    by_person: Dict[str, List[str]] = {}
    for role, person in people.items():
        if person and person.strip() and person.strip().lower() not in {"not applicable", "n/a", "—", "-", ""}:
            key = person.strip().lower()
            by_person.setdefault(key, []).append(role)

    excluded_roles: set[str] = set()
    MAX_ROLES = 2
    for person_key, roles in by_person.items():
        if len(roles) <= MAX_ROLES:
            continue
        # Sort by payout descending, keep top 2
        sorted_roles = sorted(roles, key=lambda r: amounts.get(r, 0), reverse=True)
        for excess_role in sorted_roles[MAX_ROLES:]:
            excluded_roles.add(excess_role)
    return excluded_roles


def matrix_amount(margin: Optional[Decimal], hours: Decimal) -> int:
    """Return INR incentive amount from TABLE 5."""
    if margin is None or hours < ZERO:
        return 0
    if hours <= 40:
        idx = 0
    elif hours <= 80:
        idx = 1
    elif hours <= 120:
        idx = 2
    elif hours <= 160:
        idx = 3
    else:
        idx = 4
    for low, high, values in BANDS:
        if low <= margin <= high:
            return values[idx]
    return 0


def _line(c: Candidate, role: str, person: Optional[str], amount: int, hours: Decimal,
          eligible: bool, reason: str, kind: str = "RECURRING") -> LineDraft:
    return LineDraft(
        c.id, c.candidate_name, role, (person or "—").strip(), kind,
        "Sambhaji Nagar margin x hours", eligible, Decimal(amount),
        Decimal("1") if eligible else ZERO, Decimal(amount) if eligible else ZERO,
        hours, c.margin, reason,
        [json.dumps({
            "margin": str(c.margin),
            "hours": str(hours),
            "organization": c.organization or "",
            "recruiter_location": c.recruiter_location or "",
            "start_month": c.start_date.strftime("%Y-%m") if c.start_date else "",
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "contract_type": c.contract_type or "",
            "candidate_source": c.candidate_source or "",
            **({
                "exemption_status": EXEMPTED_MISSING_RECRUITER_MASTER,
                "exemption_reason": EXEMPTION_REASON_TEXT,
            } if reason == EXEMPTED_MISSING_RECRUITER_MASTER else {}),
        })]
    )


def calculate_placement(
    c: Candidate,
    *,
    hours: Decimal,
    payment_status: str,
    coordinators: Dict[str, CoordinatorRecord],
    paid_keys: Optional[set[str]] = None,
    cycle_end: Optional[date] = None,
) -> List[LineDraft]:
    """
    Calculate all incentive lines for one Sambhaji Nagar candidate placement.

    Rules from document:
    1. Organisation must be Bravens, Ampcus Inc., or ITech
    2. Recruiter location must be Sambhaji Nagar
    3. Full-Time contract type is excluded
    4. Recruiter and Leadership recurring/fixed incentive
       - <160 hrs: blocked until client payment received
       - >=160 hrs: no payment gate
    5. Recruiter LEFT/NOTICE: not eligible
    """
    paid = payment_status.upper() in {"RECEIVED", "PAYMENT_RECEIVED", "NOT_APPLICABLE"}
    requires_payment = hours < Decimal("160")
    completed_160 = hours >= Decimal("160")

    # Recruiter employment status — missing from Recruiter Master is not LEFT/NOTICE
    coord_rec = lookup_coordinator(coordinators, c.recruiter)
    if coordinators and (c.recruiter or "").strip() and not coord_rec:
        recruiter_status = "MISSING"
    else:
        recruiter_status = getattr(coord_rec, "employment_status", "ACTIVE")
        recruiter_status = getattr(recruiter_status, "value", str(recruiter_status)).upper()

    # Source / location validation
    org_val = str(c.organization or "").strip().lower()
    loc_valid = is_valid_sn_location(c.recruiter_location)

    # Recruiter incentive amount from matrix
    amount = matrix_amount(c.margin, hours)

    # Blocking checks
    blocked = ""
    if cycle_end and c.start_date and c.start_date > cycle_end:
        blocked = "NOT_YET_STARTED"
        amount = 0
    elif org_val not in VALID_ORGS:
        blocked = "INVALID_SOURCE"
        amount = 0
    elif not loc_valid:
        blocked = "INVALID_LOCATION"
        amount = 0
    elif (c.contract_type or "").strip().upper() == "FULLTIME":
        blocked = "FULL_TIME"
        amount = 0
    elif requires_payment and not paid:
        blocked = "PAYMENT_PENDING"
    elif not amount:
        blocked = "MARGIN_OR_HOURS_OUTSIDE_MATRIX"

    base_recruiter_amount = 0 if blocked else amount

    people = {
        "Recruiter": c.recruiter,
        "Team Lead": c.team_lead,
        "Manager": c.manager,
        "Senior Manager": c.senior_manager,
        "CRM": c.crm,
        "Associate Director": c.associate_director,
        "Center Head": c.center_head,
    }

    amounts = {
        "Recruiter": base_recruiter_amount,
        "Team Lead": FIXED.get("Team Lead", 0),
        "Manager": FIXED.get("Manager", 0),
        "Senior Manager": FIXED.get("Senior Manager", 0),
        "CRM": FIXED.get("CRM", 0),
        "Associate Director": FIXED.get("Associate Director", 0),
        "Center Head": FIXED.get("Center Head", 0),
    }

    excluded_roles = _limit_roles_sambhaji(people, amounts)

    # Recruiter eligibility
    if "Recruiter" in excluded_roles:
        recruiter_reason = "EXCEEDED_MAX_ROLES"
        recruiter_ok = False
    elif recruiter_status == "MISSING":
        recruiter_reason = EXEMPTED_MISSING_RECRUITER_MASTER
        recruiter_ok = False
    elif recruiter_status == "LEFT":
        recruiter_reason = "COORDINATOR_LEFT"
        recruiter_ok = False
    elif recruiter_status == "NOTICE":
        recruiter_reason = "COORDINATOR_ON_NOTICE"
        recruiter_ok = False
    else:
        recruiter_reason = blocked or "ELIGIBLE"
        recruiter_ok = bool(c.recruiter) and not blocked

    recruiter_amount = amount if recruiter_ok else 0

    lines: List[LineDraft] = [
        _line(c, "Recruiter", c.recruiter, recruiter_amount, hours, recruiter_ok, recruiter_reason)
    ]

    # Leadership ONE_TIME lines
    for role, person in {
        "Team Lead":          c.team_lead,
        "Manager":            c.manager,
        "Senior Manager":     c.senior_manager,
        "CRM":                c.crm,
        "Associate Director": c.associate_director,
        "Center Head":        c.center_head,
        "Director":           getattr(c, "director", None),
    }.items():
        if not person or person.strip().lower() in {"not applicable", "n/a", "—", "-", ""}:
            continue

        if role not in FIXED:
            coord_rec = lookup_coordinator(coordinators, person)
            if coordinators and not coord_rec:
                lines.append(_line(c, role, person, 0, hours, False, EXEMPTED_MISSING_RECRUITER_MASTER, "ONE_TIME"))
            continue

        fixed_amount = FIXED.get(role, 0)
        
        coord_rec = lookup_coordinator(coordinators, person)
        
        person_clean = person.strip().lower()
        # Deduplication check
        key = f"{c.id}|ONE_TIME|{role}|{person_clean}"
        
        # Check coordinator master status
        if paid_keys and key in paid_keys:
            lead_eligible = False
            lead_reason = "ALREADY_PAID"
        elif role in excluded_roles:
            lead_eligible = False
            lead_reason = "EXCEEDED_MAX_ROLES"
        elif not coord_rec:
            lead_eligible = False
            lead_reason = EXEMPTED_MISSING_RECRUITER_MASTER
        else:
            coord_status = getattr(getattr(coord_rec, "employment_status", None), "value", getattr(coord_rec, "employment_status", "ACTIVE"))
            coord_status_str = str(coord_status).upper()
            if coord_status_str in {"LEFT", "NOTICE"}:
                lead_eligible = False
                lead_reason = "COORDINATOR_LEFT" if coord_status_str == "LEFT" else "COORDINATOR_ON_NOTICE"
            elif blocked and blocked != "PAYMENT_PENDING":
                lead_eligible = False
                lead_reason = blocked
            elif hours < Decimal("160"):
                lead_eligible = False
                lead_reason = "HOURS_UNDER_160"
            else:
                lead_eligible = True
                lead_reason = "ELIGIBLE"

        lead_amount = fixed_amount if lead_eligible else 0

        lines.append(_line(c, role, person, lead_amount, hours, lead_eligible, lead_reason, "ONE_TIME"))

    return lines


def special_average(lines: Sequence[LineDraft]) -> List[LineDraft]:
    """
    Recruiter Special Incentive (Multiple Placements, Same Month).

    Per document:
    - Only Recruiters with 2+ placements >= 160 hours.
    - Bonus = average of all eligible placement incentives.
    - Placements < 160 hours do NOT qualify.
    """
    groups: Dict[Tuple[str, str], List[LineDraft]] = {}
    for line in lines:
        if line.role == "Recruiter" and line.eligible and line.hours >= Decimal("160"):
            start_month = ""
            if line.explanation:
                try:
                    meta = json.loads(line.explanation[0])
                    start_month = meta.get("start_month", "")
                except Exception:
                    pass
            if start_month:
                groups.setdefault((line.person.strip().lower(), start_month), []).append(line)

    extras: List[LineDraft] = []
    for (person_lower, start_month), items in groups.items():
        if len(items) >= 2:
            total = sum((item.amount for item in items), ZERO)
            avg = total / Decimal(len(items))
            first = items[0]
            extras.append(LineDraft(
                first.candidate_id,
                f"Special Bonus: {len(items)} placements ({first.person}) [{start_month}]",
                "Recruiter",
                first.person,
                "SPECIAL",
                "Sambhaji Nagar multiple-placement average",
                True, avg, Decimal("1"), avg, ZERO, first.margin,
                "Eligible recruiter multiple-placement average bonus",
                [json.dumps({
                    "placements": len(items),
                    "individual_incentives": [str(i.amount) for i in items],
                    "average_bonus": str(avg),
                    "start_month": start_month,
                    "note": "Special incentive: average of 160+ hour placements starting in same month",
                })],
            ))
    return list(lines) + extras


def build_sn_validations(lines: List[LineDraft]) -> List[dict]:
    """Build summary validation cards for the Calculation step UI."""
    counts = {
        "sn_recruiter_eligible": 0,
        "sn_payment_pending": 0,
        "sn_outside_matrix": 0,
        "sn_invalid_source": 0,
        "sn_invalid_location": 0,
        "sn_full_time": 0,
        "sn_recruiter_left": 0,
        "sn_not_yet_started": 0,
    }
    for line in lines:
        if line.role != "Recruiter":
            continue
        if line.eligible:
            counts["sn_recruiter_eligible"] += 1
        elif line.reason == "PAYMENT_PENDING":
            counts["sn_payment_pending"] += 1
        elif line.reason == "MARGIN_OR_HOURS_OUTSIDE_MATRIX":
            counts["sn_outside_matrix"] += 1
        elif line.reason == "INVALID_SOURCE":
            counts["sn_invalid_source"] += 1
        elif line.reason == "INVALID_LOCATION":
            counts["sn_invalid_location"] += 1
        elif line.reason == "FULL_TIME":
            counts["sn_full_time"] += 1
        elif line.reason in {"COORDINATOR_LEFT", "COORDINATOR_ON_NOTICE"}:
            counts["sn_recruiter_left"] += 1
        elif line.reason == "NOT_YET_STARTED":
            counts["sn_not_yet_started"] += 1

    return [
        {"check_key": "sn_recruiter_eligible", "severity": "GREEN" if counts["sn_recruiter_eligible"] > 0 else "YELLOW",
         "count": counts["sn_recruiter_eligible"], "message": "Sambhaji Nagar: Eligible recruiter placements", "details_json": None},
        {"check_key": "sn_payment_pending", "severity": "YELLOW" if counts["sn_payment_pending"] > 0 else "GREEN",
         "count": counts["sn_payment_pending"], "message": "Placements awaiting client payment (<160 hrs)", "details_json": None},
        {"check_key": "sn_outside_matrix", "severity": "YELLOW" if counts["sn_outside_matrix"] > 0 else "GREEN",
         "count": counts["sn_outside_matrix"], "message": "Placements outside incentive matrix (margin/hours range)", "details_json": None},
        {"check_key": "sn_invalid_source", "severity": "RED" if counts["sn_invalid_source"] > 0 else "GREEN",
         "count": counts["sn_invalid_source"], "message": "Invalid organization (must be Bravens, Ampcus Inc., or ITech)", "details_json": None},
        {"check_key": "sn_invalid_location", "severity": "RED" if counts["sn_invalid_location"] > 0 else "GREEN",
         "count": counts["sn_invalid_location"], "message": "Invalid recruiter location (must be Sambhaji Nagar)", "details_json": None},
        {"check_key": "sn_full_time", "severity": "YELLOW" if counts["sn_full_time"] > 0 else "GREEN",
         "count": counts["sn_full_time"], "message": "Placements excluded: Full-Time contract", "details_json": None},
        {"check_key": "sn_recruiter_left", "severity": "YELLOW" if counts["sn_recruiter_left"] > 0 else "GREEN",
         "count": counts["sn_recruiter_left"], "message": "Placements excluded: Recruiter left / on notice", "details_json": None},
        {"check_key": "sn_not_yet_started", "severity": "YELLOW" if counts["sn_not_yet_started"] > 0 else "GREEN",
         "count": counts["sn_not_yet_started"], "message": "Placements excluded: Start date is after incentive month", "details_json": None},
    ]
