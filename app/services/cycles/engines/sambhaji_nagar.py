"""Sambhaji Nagar margin x hours engine.

Business rules (per Incentive Calculation Process document + management amendments):
 - Applicable organisations: Bravens, Ampcus Inc., ITech
 - Applicable location: Sambhaji Nagar (recruiter_location)
 - W2 / C2C placements: recruiter incentive from margin x hours matrix (TABLE 5)
 - FULLTIME placements: routed to the FTE incentive path (NOT excluded any more)
      * Gate 1: candidate must have completed >= 90 days (the uploaded 'Hours Worked'
        column contains the number of days for FTE candidates)
      * Gate 2: client payment received
      * Recruiter incentive based on Finder's Fee threshold + number of FTE placements
        placed by the same recruiter in the same calendar month
      * Leadership roles receive fixed ONE_TIME amounts per placement
 - Client payment received is required for ALL candidates (no hours-based exemption)
 - Recruiter incentive amount bucket (W2/C2C) is determined by the candidate's CUMULATIVE
   UNPAID hours (hours from prior finalized SN cycles where payment was not received +
   current cycle hours). Once hours are paid, they are not counted again.
 - Leadership ONE_TIME incentive (W2/C2C):
     * Requires cumulative lifetime hours >= 160 (all past + current)
     * Requires client payment received in the current cycle
     * Both conditions must be satisfied; paid only once (dedup via paid_keys)
 - Recruiter Special Incentive: only for W2/C2C recruiters with 2+ eligible placements in
   the same cycle month (FTE placements are NOT included in the special incentive pool)
 - AVP and Center Head have the same fixed incentive amount
 - Director and CRM have the same fixed incentive amount
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Set, Tuple

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
# Bucket is determined by CUMULATIVE hours across all finalized SN cycles + current cycle.
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
# AVP = Center Head amount (1750); Director = CRM amount (1000)
FIXED: Dict[str, int] = {
    "Team Lead":           500,
    "Manager":            1000,
    "Senior Manager":     1500,
    "CRM":                1000,
    "Associate Director": 1750,
    "Center Head":        1750,
    "AVP":                1750,   # same as Center Head
    "Director":           1000,   # same as CRM
}

VALID_ORGS = {"bravens", "ampcus inc", "ampcus inc.", "itech"}

# Valid Sambhaji Nagar location keywords
VALID_LOCATIONS = {"sambhaji nagar", "sambhajinagar", "sambhaji"}

# ── FTE (Full-Time) Incentive Constants ───────────────────────────────────────
# Finder's Fee threshold that separates the two recruiter slab tiers.
FTE_FINDER_FEE_THRESHOLD = Decimal("4500")

# FTE_RECRUITER_SLABS[finder_fee_above_threshold][placement_count_bucket]
# placement_count_bucket: 0 = 1 placement, 1 = 2 placements, 2 = 3+ placements
FTE_RECRUITER_SLABS: Dict[bool, Tuple[int, int, int]] = {
    False: (15000, 18000, 20000),   # Finder's fee below $4,500
    True:  (20000, 25000, 30000),   # Finder's fee above $4,500
}

# FTE_FIXED — fixed ONE_TIME amounts for leadership roles per FTE placement
# (from TABLE 2 in document)
FTE_FIXED: Dict[str, int] = {
    "Team Lead":           1000,
    "Manager":             1500,
    "CRM":                 1500,
    "Associate Director":  4000,
    "Center Head":         4000,
    "AVP":                 4000,   # same as Center Head for FTE
    "Director":            1500,   # same as CRM for FTE
    "Senior Manager":      1500,
}

# Minimum days a FTE candidate must have completed to be eligible for incentive
FTE_MIN_DAYS = Decimal("90")


def is_fte_contract(contract_type: Optional[str]) -> bool:
    """Return True when the candidate is a Full-Time placement."""
    return (contract_type or "").strip().upper() in {"FULLTIME", "FULL_TIME", "FT"}


def fte_recruiter_amount(
    finder_fee_above_threshold: bool,
    placement_count_this_month: int,
) -> int:
    """Return the INR recruiter incentive for one FTE placement."""
    slabs = FTE_RECRUITER_SLABS[finder_fee_above_threshold]
    if placement_count_this_month >= 3:
        return slabs[2]
    if placement_count_this_month == 2:
        return slabs[1]
    return slabs[0]


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
    """Return INR incentive amount from TABLE 5.

    ``hours`` should be the candidate's CUMULATIVE hours across all finalized
    SN cycles plus the current cycle, so that the correct bucket is applied.
    """
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
          eligible: bool, reason: str, kind: str = "RECURRING",
          cumulative_hours: Optional[Decimal] = None) -> LineDraft:
    return LineDraft(
        c.id, c.candidate_name, role, (person or "—").strip(), kind,
        "Sambhaji Nagar margin x hours", eligible, Decimal(amount),
        Decimal("1") if eligible else ZERO, Decimal(amount) if eligible else ZERO,
        hours, c.margin, reason,
        [json.dumps({
            "margin": str(c.margin),
            "hours": str(hours),
            "cumulative_hours": str(cumulative_hours) if cumulative_hours is not None else str(hours),
            "organization": c.organization or "",
            "recruiter_location": c.recruiter_location or "",
            "start_month": c.start_date.strftime("%Y-%m") if c.start_date else "",
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "contract_type": c.contract_type or "",
            "candidate_source": c.candidate_source or "",
            "external_candidate_id": c.activity_id or c.start_id or c.external_candidate_id or "",
            "candidate_id": c.activity_id or c.start_id or c.external_candidate_id or "",
            **(  {
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
    cycle_end=None,
    recruiter_matrix_hours: Optional[Decimal] = None,
    leadership_lifetime_hours: Optional[Decimal] = None,
    already_approved_this_month: Optional[Decimal] = None,
) -> List[LineDraft]:
    """
    Calculate all incentive lines for one Sambhaji Nagar candidate placement.

    Business rules:
    1. Organisation must be Bravens, Ampcus Inc., or ITech
    2. Recruiter location must be Sambhaji Nagar
    3. Full-Time contract type is excluded
    4. Client payment received is required for ALL candidates (regardless of hours)
    5. Recruiter incentive matrix bucket is determined by CUMULATIVE UNPAID hours
       (prior finalized SN cycles where payment was pending + current cycle hours).
       Once hours are paid, they are not accumulated again.
    6. Leadership ONE_TIME incentive:
       - Released only when cumulative lifetime hours >= 160
       - Also requires client payment received in the current cycle
       - Paid only once per candidate/role/person (dedup via paid_keys)
    7. Recruiter LEFT/NOTICE: not eligible
    8. AVP has same fixed amount as Center Head; Director has same fixed amount as CRM

    Args:
        hours: current cycle hours for this candidate
        recruiter_matrix_hours: unpaid backlog hours + current cycle hours
        leadership_lifetime_hours: total hours including all prior finalized SN cycles
    """
    # Resolve hours
    recruiter_hours: Decimal = recruiter_matrix_hours if recruiter_matrix_hours is not None else hours
    lifetime_hours: Decimal = leadership_lifetime_hours if leadership_lifetime_hours is not None else hours

    paid = payment_status.upper() in {"RECEIVED", "PAYMENT_RECEIVED", "NOT_APPLICABLE"}

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

    # Recruiter incentive amount from matrix — using UNPAID backlog hours for bucket selection
    amount = matrix_amount(c.margin, recruiter_hours)

    # Blocking checks (hard blocks abort both recruiter and leadership)
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
    elif not paid:
        # Payment gate applies to ALL candidates regardless of hours worked
        blocked = "PAYMENT_PENDING"
    elif not amount:
        blocked = "MARGIN_OR_HOURS_OUTSIDE_MATRIX"

    base_recruiter_amount = 0 if blocked else amount

    people = {
        "Recruiter":          c.recruiter,
        "Team Lead":          c.team_lead,
        "Manager":            c.manager,
        "Senior Manager":     c.senior_manager,
        "CRM":                c.crm,
        "Associate Director": c.associate_director,
        "Center Head":        c.center_head,
        "AVP":                getattr(c, "avp", None),
        "Director":           getattr(c, "director", None),
    }

    amounts = {role: FIXED.get(role, 0) for role in people}
    amounts["Recruiter"] = base_recruiter_amount

    excluded_roles = _limit_roles_sambhaji(people, amounts)

    # ── Recruiter eligibility ──────────────────────────────────────────────────
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
    elif already_approved_this_month is not None and hours == already_approved_this_month and hours > ZERO:
        recruiter_reason = "Already Paid in Previous Cycle"
        recruiter_ok = False
    else:
        recruiter_reason = blocked or "ELIGIBLE"
        recruiter_ok = bool(c.recruiter) and not blocked

    recruiter_amount = amount if recruiter_ok else 0

    lines: List[LineDraft] = [
        # Pass recruiter_hours to BOTH the actual `hours` and `cumulative_hours` fields
        # This ensures that when the line is paid, it registers as having paid the full accumulated amount
        _line(c, "Recruiter", c.recruiter, recruiter_amount, recruiter_hours,
              recruiter_ok, recruiter_reason, "RECURRING", recruiter_hours)
    ]

    # ── Leadership ONE_TIME lines ──────────────────────────────────────────────
    # Eligibility requires BOTH:
    #   (a) cumulative lifetime hours >= 160 (across all finalized SN cycles + current)
    #   (b) client payment received in this cycle
    for role, person in {
        "Team Lead":          c.team_lead,
        "Manager":            c.manager,
        "Senior Manager":     c.senior_manager,
        "CRM":                c.crm,
        "Associate Director": c.associate_director,
        "Center Head":        c.center_head,
        "AVP":                getattr(c, "avp", None),
        "Director":           getattr(c, "director", None),
    }.items():
        if not person or person.strip().lower() in {"not applicable", "n/a", "—", "-", ""}:
            continue

        if role not in FIXED:
            # Role exists on candidate but has no fixed amount — record for audit only
            coord_rec_l = lookup_coordinator(coordinators, person)
            if coordinators and not coord_rec_l:
                lines.append(_line(c, role, person, 0, hours, False,
                                   EXEMPTED_MISSING_RECRUITER_MASTER, "ONE_TIME", lifetime_hours))
            continue

        fixed_amount = FIXED[role]
        coord_rec_l = lookup_coordinator(coordinators, person)

        person_clean = person.strip().lower()
        # Deduplication key — prevents paying the same ONE_TIME twice across cycles
        key = f"{c.id}|ONE_TIME|{role}|{person_clean}"

        if paid_keys and key in paid_keys:
            lead_eligible = False
            lead_reason = "ALREADY_PAID"
        elif role in excluded_roles:
            lead_eligible = False
            lead_reason = "EXCEEDED_MAX_ROLES"
        elif not coord_rec_l:
            lead_eligible = False
            lead_reason = EXEMPTED_MISSING_RECRUITER_MASTER
        else:
            coord_status = getattr(
                getattr(coord_rec_l, "employment_status", None),
                "value",
                getattr(coord_rec_l, "employment_status", "ACTIVE"),
            )
            coord_status_str = str(coord_status).upper()
            if coord_status_str == "LEFT":
                lead_eligible = False
                lead_reason = "COORDINATOR_LEFT"
            elif coord_status_str == "NOTICE":
                lead_eligible = False
                lead_reason = "COORDINATOR_ON_NOTICE"
            elif blocked and blocked not in {"PAYMENT_PENDING"}:
                # Hard blocks (invalid org, location, full-time, not started)
                lead_eligible = False
                lead_reason = blocked
            elif lifetime_hours < Decimal("160"):
                # Cumulative hours across all SN cycles have not reached 160 yet
                lead_eligible = False
                lead_reason = "CUMULATIVE_HOURS_UNDER_160"
            elif not paid:
                # Payment not yet received — hold until payment arrives in a later cycle
                lead_eligible = False
                lead_reason = "PAYMENT_PENDING"
            else:
                lead_eligible = True
                lead_reason = "ELIGIBLE"

        lead_amount = fixed_amount if lead_eligible else 0
        lines.append(_line(c, role, person, lead_amount, lifetime_hours,
                           lead_eligible, lead_reason, "ONE_TIME", lifetime_hours))

    return lines


def calculate_fte_placement(
    c: Candidate,
    *,
    days_completed: Decimal,
    payment_status: str,
    coordinators: Dict[str, CoordinatorRecord],
    paid_keys: Optional[set[str]] = None,
    cycle_end=None,
    finder_fee_above_threshold: bool = False,
    placement_count_this_month: int = 1,
) -> List[LineDraft]:
    """
    Calculate incentive lines for one Sambhaji Nagar Full-Time (FTE) candidate.

    Eligibility gates:
    1. days_completed >= 90  (the 'Hours Worked' column in the template holds days for FTE)
    2. client payment received

    Recruiter incentive is a fixed one-time amount per FTE placement, determined by:
    - Whether the finder's fee exceeds $4,500 (finder_fee_above_threshold)
    - How many FTE placements the same recruiter made in the same calendar month

    Leadership roles (Team Lead, Manager, CRM, AD, Center Head) each receive a fixed
    ONE_TIME amount per FTE placement regardless of placement volume.
    """
    paid = payment_status.upper() in {"RECEIVED", "PAYMENT_RECEIVED", "NOT_APPLICABLE"}

    # Source / location validation
    org_val = str(c.organization or "").strip().lower()
    loc_valid = is_valid_sn_location(c.recruiter_location)

    # Recruiter employment status
    coord_rec = lookup_coordinator(coordinators, c.recruiter)
    if coordinators and (c.recruiter or "").strip() and not coord_rec:
        recruiter_status = "MISSING"
    else:
        recruiter_status = getattr(coord_rec, "employment_status", "ACTIVE")
        recruiter_status = getattr(recruiter_status, "value", str(recruiter_status)).upper()

    # Hard blocks
    hard_blocked = ""
    if cycle_end and c.start_date and c.start_date > cycle_end:
        hard_blocked = "NOT_YET_STARTED"
    elif org_val not in VALID_ORGS:
        hard_blocked = "INVALID_SOURCE"
    elif not loc_valid:
        hard_blocked = "INVALID_LOCATION"

    # Eligibility gates
    days_gate_ok = days_completed >= FTE_MIN_DAYS
    payment_gate_ok = paid

    # Build recruiter incentive amount
    if hard_blocked:
        recruiter_blocked = hard_blocked
        recruiter_ok = False
        rec_amount = 0
    elif recruiter_status == "MISSING":
        recruiter_blocked = EXEMPTED_MISSING_RECRUITER_MASTER
        recruiter_ok = False
        rec_amount = 0
    elif recruiter_status in {"LEFT", "NOTICE"}:
        recruiter_blocked = (
            "COORDINATOR_LEFT" if recruiter_status == "LEFT" else "COORDINATOR_ON_NOTICE"
        )
        recruiter_ok = False
        rec_amount = 0
    elif not days_gate_ok:
        recruiter_blocked = "FTE_90_DAY_NOT_MET"
        recruiter_ok = False
        rec_amount = 0
    elif not payment_gate_ok:
        recruiter_blocked = "PAYMENT_PENDING"
        recruiter_ok = False
        rec_amount = 0
    else:
        recruiter_blocked = ""
        recruiter_ok = bool(c.recruiter)
        rec_amount = fte_recruiter_amount(finder_fee_above_threshold, placement_count_this_month)

    base_explanation = json.dumps({
        "contract_type": "FULLTIME",
        "days_completed": str(days_completed),
        "fte_min_days": str(FTE_MIN_DAYS),
        "finder_fee_above_threshold": finder_fee_above_threshold,
        "placement_count_this_month": placement_count_this_month,
        "payment_status": payment_status,
        "organization": c.organization or "",
        "recruiter_location": c.recruiter_location or "",
        "external_candidate_id": c.activity_id or c.start_id or c.external_candidate_id or "",
        "candidate_id": c.activity_id or c.start_id or c.external_candidate_id or "",
    })

    lines: List[LineDraft] = [
        _line(
            c, "Recruiter", c.recruiter, rec_amount, days_completed,
            recruiter_ok, recruiter_blocked or "ELIGIBLE", "ONE_TIME", days_completed
        )
    ]
    # Patch the explanation with FTE detail
    lines[0].explanation = [base_explanation]

    # ── Leadership ONE_TIME lines ──────────────────────────────────────────────
    # Each eligible leadership role gets a fixed amount once per FTE placement.
    for role, person in {
        "Team Lead":          c.team_lead,
        "Manager":            c.manager,
        "Senior Manager":     c.senior_manager,
        "CRM":                c.crm,
        "Associate Director": c.associate_director,
        "Center Head":        c.center_head,
        "AVP":                getattr(c, "avp", None),
        "Director":           getattr(c, "director", None),
    }.items():
        if not person or person.strip().lower() in {"not applicable", "n/a", "—", "-", ""}:
            continue
        if role not in FTE_FIXED:
            continue

        fixed_amount = FTE_FIXED[role]
        coord_rec_l = lookup_coordinator(coordinators, person)
        person_clean = person.strip().lower()
        key = f"{c.id}|ONE_TIME|FTE|{role}|{person_clean}"

        if paid_keys and key in paid_keys:
            lead_eligible = False
            lead_reason = "ALREADY_PAID"
        elif hard_blocked:
            lead_eligible = False
            lead_reason = hard_blocked
        elif not coord_rec_l:
            lead_eligible = False
            lead_reason = EXEMPTED_MISSING_RECRUITER_MASTER
        else:
            coord_status = getattr(
                getattr(coord_rec_l, "employment_status", None), "value",
                getattr(coord_rec_l, "employment_status", "ACTIVE"),
            )
            coord_status_str = str(coord_status).upper()
            if coord_status_str == "LEFT":
                lead_eligible = False
                lead_reason = "COORDINATOR_LEFT"
            elif coord_status_str == "NOTICE":
                lead_eligible = False
                lead_reason = "COORDINATOR_ON_NOTICE"
            elif not days_gate_ok:
                lead_eligible = False
                lead_reason = "FTE_90_DAY_NOT_MET"
            elif not payment_gate_ok:
                lead_eligible = False
                lead_reason = "PAYMENT_PENDING"
            else:
                lead_eligible = True
                lead_reason = "ELIGIBLE"

        lead_amount = fixed_amount if lead_eligible else 0
        line = _line(
            c, role, person, lead_amount, days_completed,
            lead_eligible, lead_reason, "ONE_TIME", days_completed
        )
        line.explanation = [base_explanation]
        lines.append(line)

    return lines


def calculate_special_incentives(
    all_sn_candidates: List[Any],
    lifetime_hours_map: Dict[int, Decimal],
    paid_specials_map: Dict[Tuple[str, str], Decimal],
    cycle_month: Optional[str]
) -> List[LineDraft]:
    """
    Recruiter Special Incentive (Multiple Placements, Same Start Month).
    Calculates average bonus for recruiters who have >= 2 placements starting in the same month
    that have achieved >= 160 cumulative hours.
    """
    from collections import defaultdict
    import json

    groups = defaultdict(list)
    for c in all_sn_candidates:
        if not c.recruiter or not c.start_date:
            continue
        lifetime_hours = lifetime_hours_map.get(c.id, ZERO)
        if lifetime_hours < Decimal("160"):
            continue
        
        person_lower = str(c.recruiter).strip().lower()
        start_month = c.start_date.strftime("%Y-%m")
        groups[(person_lower, start_month)].append(c)

    extras: List[LineDraft] = []
    for (person_lower, start_month), candidates in groups.items():
        if len(candidates) >= 2:
            total_base = ZERO
            for c in candidates:
                base_amt = matrix_amount(c.margin, Decimal("160"))
                total_base += Decimal(str(base_amt))
            
            avg_bonus = total_base / Decimal(len(candidates))
            
            previously_paid = paid_specials_map.get((person_lower, start_month), ZERO)
            payable_now = avg_bonus - previously_paid
            
            if payable_now > ZERO:
                first = candidates[0]
                extras.append(LineDraft(
                    first.id,
                    f"Special Bonus: {len(candidates)} placements ({first.recruiter}) [Start: {start_month}]",
                    "Recruiter",
                    first.recruiter,
                    "SPECIAL",
                    "Sambhaji Nagar multiple-placement average",
                    True, float(payable_now), Decimal("1"), float(payable_now), ZERO, first.margin,
                    "Eligible recruiter multiple-placement average bonus",
                    [json.dumps({
                        "start_month": start_month,
                        "placements": len(candidates),
                        "average_bonus": float(avg_bonus),
                        "previously_paid": float(previously_paid),
                        "payable_now": float(payable_now),
                        "cycle_month": cycle_month,
                        "note": "Special incentive: average of 160+ hour placements starting in same month",
                        "external_candidate_id": first.activity_id or first.start_id or first.external_candidate_id or "",
                        "candidate_id": first.activity_id or first.start_id or first.external_candidate_id or "",
                    })],
                ))
    return extras


def build_sn_validations(lines: List[LineDraft]) -> List[dict]:
    """Build summary validation cards for the Calculation step UI."""
    counts = {
        "sn_recruiter_eligible": 0,
        "sn_payment_pending": 0,
        "sn_outside_matrix": 0,
        "sn_invalid_source": 0,
        "sn_invalid_location": 0,
        "sn_full_time": 0,          # legacy: kept for old ineligible lines pre-FTE
        "sn_recruiter_left": 0,
        "sn_not_yet_started": 0,
        "sn_cumulative_hours_under_160": 0,
        "sn_fte_eligible": 0,
        "sn_fte_90_day_not_met": 0,
        "sn_fte_payment_pending": 0,
    }
    for line in lines:
        if line.role != "Recruiter":
            continue
        # Detect whether this line came from the FTE path by checking explanation payload
        is_fte_line = False
        try:
            payload = json.loads(line.explanation[0]) if line.explanation else {}
            is_fte_line = payload.get("contract_type", "") == "FULLTIME"
        except Exception:
            pass

        if line.eligible:
            if is_fte_line:
                counts["sn_fte_eligible"] += 1
            else:
                counts["sn_recruiter_eligible"] += 1
        elif line.reason == "FTE_90_DAY_NOT_MET":
            counts["sn_fte_90_day_not_met"] += 1
        elif line.reason == "PAYMENT_PENDING":
            if is_fte_line:
                counts["sn_fte_payment_pending"] += 1
            else:
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
        elif line.reason == "CUMULATIVE_HOURS_UNDER_160":
            counts["sn_cumulative_hours_under_160"] += 1

    return [
        {"check_key": "sn_recruiter_eligible", "severity": "GREEN" if counts["sn_recruiter_eligible"] > 0 else "YELLOW",
         "count": counts["sn_recruiter_eligible"], "message": "Sambhaji Nagar (W2/C2C): Eligible recruiter placements", "details_json": None},
        {"check_key": "sn_fte_eligible", "severity": "GREEN" if counts["sn_fte_eligible"] > 0 else "YELLOW",
         "count": counts["sn_fte_eligible"], "message": "Sambhaji Nagar (FTE): Eligible recruiter placements", "details_json": None},
        {"check_key": "sn_fte_90_day_not_met", "severity": "YELLOW" if counts["sn_fte_90_day_not_met"] > 0 else "GREEN",
         "count": counts["sn_fte_90_day_not_met"], "message": "FTE placements: 90-day requirement not met", "details_json": None},
        {"check_key": "sn_fte_payment_pending", "severity": "YELLOW" if counts["sn_fte_payment_pending"] > 0 else "GREEN",
         "count": counts["sn_fte_payment_pending"], "message": "FTE placements awaiting client payment", "details_json": None},
        {"check_key": "sn_payment_pending", "severity": "YELLOW" if counts["sn_payment_pending"] > 0 else "GREEN",
         "count": counts["sn_payment_pending"], "message": "W2/C2C placements awaiting client payment", "details_json": None},
        {"check_key": "sn_outside_matrix", "severity": "YELLOW" if counts["sn_outside_matrix"] > 0 else "GREEN",
         "count": counts["sn_outside_matrix"], "message": "Placements outside incentive matrix (margin/hours range)", "details_json": None},
        {"check_key": "sn_invalid_source", "severity": "RED" if counts["sn_invalid_source"] > 0 else "GREEN",
         "count": counts["sn_invalid_source"], "message": "Invalid organization (must be Bravens, Ampcus Inc., or ITech)", "details_json": None},
        {"check_key": "sn_invalid_location", "severity": "RED" if counts["sn_invalid_location"] > 0 else "GREEN",
         "count": counts["sn_invalid_location"], "message": "Invalid recruiter location (must be Sambhaji Nagar)", "details_json": None},
        {"check_key": "sn_full_time", "severity": "YELLOW" if counts["sn_full_time"] > 0 else "GREEN",
         "count": counts["sn_full_time"], "message": "Placements excluded: Full-Time contract (legacy)", "details_json": None},
        {"check_key": "sn_recruiter_left", "severity": "YELLOW" if counts["sn_recruiter_left"] > 0 else "GREEN",
         "count": counts["sn_recruiter_left"], "message": "Placements excluded: Recruiter left / on notice", "details_json": None},
        {"check_key": "sn_not_yet_started", "severity": "YELLOW" if counts["sn_not_yet_started"] > 0 else "GREEN",
         "count": counts["sn_not_yet_started"], "message": "Placements excluded: Start date is after incentive month", "details_json": None},
        {"check_key": "sn_cumulative_hours_under_160", "severity": "YELLOW" if counts["sn_cumulative_hours_under_160"] > 0 else "GREEN",
         "count": counts["sn_cumulative_hours_under_160"], "message": "Placements with cumulative hours < 160 (leadership ONE_TIME deferred)", "details_json": None},
    ]
