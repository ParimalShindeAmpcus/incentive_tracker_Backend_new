"""Nashik Division FTE (Full-Time) incentive calculation.

Rules (Nashik-only):
- Candidate must appear in the uploaded hours file (caller filters).
- Candidate Master contract type is FTE / FULLTIME.
- Finder Fee classification comes from Candidate Master (Below $4500 / Above $4500).
- Eligible only after Start Date + 90 days.
- Recruiter amount from Finder Fee tier + monthly qualifying placement count.
- If first payment received: pay remaining recruiter amount one-time after 90 days.
- If payment not received by 90 days: pay recruiter amount in equal 1/3 installments
  after 90 days (tracked via prior paid amounts).
- Hierarchy (TL, Manager, CRM, AD, Center Head): fixed one-time after 90 days;
  not subject to the recruiter 3-month installment rule.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from app.repositories.entities.candidate import Candidate
from app.repositories.entities.coordinator import CoordinatorRecord
from app.services.cycles.engines.sambhaji_nagar import (
    FTE_FIXED,
    fte_recruiter_amount,
    is_fte_contract,
)
from app.services.cycles.recruiter_master import (
    EXEMPTED_MISSING_RECRUITER_MASTER,
    EXEMPTION_REASON_TEXT,
    lookup_coordinator,
)
from app.services.incentives.nashik_calculator import LineDraft
from app.services.incentives.nashik_rules import is_nashik_office, matches_nashik_company

ZERO = Decimal("0")
FTE_MIN_DAYS = 90


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def finder_fee_above_from_master(candidate: Candidate) -> bool:
    """True when Candidate Master Finder Fees is Above $4500."""
    raw = str(getattr(candidate, "finder_fees", None) or "").strip().upper().replace(" ", "").replace("-", "").replace("$", "").replace(",", "")
    if raw in {"ABOVE500", "ABOVE_500", "ABOVE4500"}:
        return True
    if raw in {"BELOW500", "BELOW_500", "BELOW4500"}:
        return False
    fee = getattr(candidate, "finders_fee", None)
    if fee is not None:
        try:
            return Decimal(str(fee)) > Decimal("4500")
        except Exception:
            return False
    return False


def finder_fee_label(candidate: Candidate) -> str:
    raw = str(getattr(candidate, "finder_fees", None) or "NONE").strip().upper()
    if raw in {"ABOVE_500", "ABOVE500"}:
        return "Above $4500"
    if raw in {"BELOW_500", "BELOW500"}:
        return "Below $4500"
    return "None"


def ninety_day_eligible_date(start: Optional[date]) -> Optional[date]:
    if not start:
        return None
    return start + timedelta(days=FTE_MIN_DAYS)


def days_completed_from_start(start: Optional[date], as_of: Optional[date]) -> int:
    if not start or not as_of:
        return 0
    if as_of < start:
        return 0
    return (as_of - start).days


def _line(
    c: Candidate,
    role: str,
    person: Optional[str],
    amount: Decimal,
    *,
    eligible: bool,
    reason: str,
    incentive_type: str,
    hours: Decimal,
    explanation: dict,
) -> LineDraft:
    return LineDraft(
        candidate_id=c.id,
        candidate_name=c.candidate_name,
        role=role,
        person=(person or "—").strip(),
        incentive_type=incentive_type,
        rule_applied="Nashik FTE",
        eligible=eligible,
        base_incentive=amount,
        pro_rata_factor=Decimal("1") if eligible else ZERO,
        amount=amount if eligible else ZERO,
        hours=hours,
        margin=c.margin,
        reason=reason,
        explanation=[json.dumps(explanation, default=str)],
    )


def calculate_nashik_fte_placement(
    c: Candidate,
    *,
    payment_status: str,
    coordinators: Dict[str, CoordinatorRecord],
    paid_keys: Optional[set[str]] = None,
    cycle_end: Optional[date] = None,
    placement_count_this_month: int = 1,
    prior_recruiter_paid_amount: Decimal = ZERO,
) -> List[LineDraft]:
    """Calculate Nashik FTE incentive lines for one Candidate Master placement."""
    as_of = cycle_end or date.today()
    paid = payment_status.upper() in {"RECEIVED", "PAYMENT_RECEIVED", "NOT_APPLICABLE"}
    days_done = days_completed_from_start(c.start_date, as_of)
    eligible_on = ninety_day_eligible_date(c.start_date)
    days_gate_ok = days_done >= FTE_MIN_DAYS
    hours_proxy = Decimal(str(days_done))

    fee_above = finder_fee_above_from_master(c)
    full_recruiter = Decimal(
        fte_recruiter_amount(fee_above, max(1, int(placement_count_this_month)))
    )

    hard_blocked = ""
    finder_raw = str(getattr(c, "finder_fees", None) or "NONE").strip().upper()
    if cycle_end and c.start_date and c.start_date > cycle_end:
        hard_blocked = "NOT_YET_STARTED"
    elif not matches_nashik_company(c.candidate_source, c.organization):
        hard_blocked = "INVALID_SOURCE"
    elif not is_nashik_office(c.recruiter_location):
        hard_blocked = "INVALID_LOCATION"
    elif finder_raw in {"", "NONE", "NULL", "N/A", "NA"}:
        hard_blocked = "FINDER_FEE_NOT_SET"

    coord_rec = lookup_coordinator(coordinators, c.recruiter)
    if coordinators and (c.recruiter or "").strip() and not coord_rec:
        recruiter_status = "MISSING"
    else:
        recruiter_status = getattr(coord_rec, "employment_status", "ACTIVE")
        recruiter_status = getattr(recruiter_status, "value", str(recruiter_status)).upper()

    base_meta = {
        "division": "Nashik",
        "nashik_fte": True,
        "contract_type": "FULLTIME",
        "candidate_type": "FTE",
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "ninety_day_eligible_date": eligible_on.isoformat() if eligible_on else None,
        "days_completed": days_done,
        "fte_min_days": FTE_MIN_DAYS,
        "finder_fees": getattr(c, "finder_fees", None) or "NONE",
        "finder_fee_label": finder_fee_label(c),
        "finder_fee_above_threshold": fee_above,
        "placement_count_this_month": placement_count_this_month,
        "payment_status": payment_status,
        "payment_received": paid,
        "full_recruiter_incentive": str(full_recruiter),
        "prior_recruiter_paid_amount": str(prior_recruiter_paid_amount),
        "organization": c.organization or "",
        "recruiter_location": c.recruiter_location or "",
        "external_candidate_id": c.activity_id or c.start_id or c.external_candidate_id or "",
        "candidate_id": c.activity_id or c.start_id or c.external_candidate_id or "",
    }

    # ── Recruiter ────────────────────────────────────────────────────────────
    recruiter_amount = ZERO
    recruiter_ok = False
    recruiter_reason = "ELIGIBLE"
    payment_schedule = "ONE_TIME"

    if hard_blocked:
        recruiter_reason = hard_blocked
    elif recruiter_status == "MISSING":
        recruiter_reason = EXEMPTED_MISSING_RECRUITER_MASTER
    elif recruiter_status in {"LEFT", "NOTICE"}:
        recruiter_reason = "COORDINATOR_LEFT" if recruiter_status == "LEFT" else "COORDINATOR_ON_NOTICE"
    elif not days_gate_ok:
        recruiter_reason = "FTE_90_DAY_NOT_MET"
    elif not (c.recruiter or "").strip():
        recruiter_reason = "MISSING_RECRUITER"
    else:
        remaining = money(full_recruiter - Decimal(str(prior_recruiter_paid_amount or 0)))
        if remaining <= ZERO:
            recruiter_reason = "ALREADY_PAID"
        elif paid:
            # Payment received: pay remaining one-time after 90 days.
            recruiter_ok = True
            recruiter_amount = remaining
            payment_schedule = "ONE_TIME_AFTER_90_DAYS"
            recruiter_reason = "ELIGIBLE"
        else:
            # Payment not received: equal thirds after 90 days.
            installment = money(full_recruiter / Decimal("3"))
            recruiter_ok = True
            recruiter_amount = money(min(installment, remaining))
            prior_n = int(
                (Decimal(str(prior_recruiter_paid_amount or 0)) / installment).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            ) if installment > ZERO else 0
            payment_schedule = f"INSTALLMENT_{min(prior_n + 1, 3)}/3"
            recruiter_reason = "ELIGIBLE_PAYMENT_PENDING_INSTALLMENT"

    rec_meta = {
        **base_meta,
        "payment_schedule": payment_schedule,
        **(
            {
                "exemption_status": EXEMPTED_MISSING_RECRUITER_MASTER,
                "exemption_reason": EXEMPTION_REASON_TEXT,
            }
            if recruiter_reason == EXEMPTED_MISSING_RECRUITER_MASTER
            else {}
        ),
    }
    lines: List[LineDraft] = [
        _line(
            c,
            "Recruiter",
            c.recruiter,
            recruiter_amount,
            eligible=recruiter_ok,
            reason=recruiter_reason,
            incentive_type="FULL_TIME",
            hours=hours_proxy,
            explanation=rec_meta,
        )
    ]

    # ── Hierarchy one-time (after 90 days; not installment-based) ─────────────
    for role, person in {
        "Team Lead": c.team_lead,
        "Manager": c.manager,
        "CRM": c.crm,
        "Associate Director": c.associate_director,
        "Center Head": c.center_head,
    }.items():
        if not person or person.strip().lower() in {"not applicable", "n/a", "—", "-", ""}:
            continue
        fixed_amount = Decimal(FTE_FIXED.get(role, 0))
        if fixed_amount <= ZERO:
            continue

        person_clean = person.strip().lower()
        key = f"{c.id}|ONE_TIME|FTE|{role}|{person_clean}"
        # Also block standard one-time key shape used by paid_one_time_keys.
        std_key = f"{c.id}|ONE_TIME|{role}|{person_clean}"

        coord_rec_l = lookup_coordinator(coordinators, person)
        if paid_keys and (key in paid_keys or std_key in paid_keys):
            lead_eligible = False
            lead_reason = "ALREADY_PAID"
        elif hard_blocked:
            lead_eligible = False
            lead_reason = hard_blocked
        elif not days_gate_ok:
            lead_eligible = False
            lead_reason = "FTE_90_DAY_NOT_MET"
        elif not coord_rec_l and coordinators:
            lead_eligible = False
            lead_reason = EXEMPTED_MISSING_RECRUITER_MASTER
        else:
            if coord_rec_l:
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
                else:
                    lead_eligible = True
                    lead_reason = "ELIGIBLE"
            else:
                lead_eligible = True
                lead_reason = "ELIGIBLE"

        lead_meta = {**base_meta, "payment_schedule": "ONE_TIME_AFTER_90_DAYS", "hierarchy_role": role}
        lines.append(
            _line(
                c,
                role,
                person,
                fixed_amount if lead_eligible else ZERO,
                eligible=lead_eligible,
                reason=lead_reason,
                incentive_type="ONE_TIME",
                hours=hours_proxy,
                explanation=lead_meta,
            )
        )

    return lines
