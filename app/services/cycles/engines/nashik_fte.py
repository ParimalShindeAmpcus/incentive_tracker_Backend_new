"""Nashik Division FTE (Full-Time) incentive calculation.

Rules (Nashik-only):
- Candidate must appear in the uploaded hours file (caller filters).
- Candidate Master contract type is FTE / FULLTIME.
- Finder Fee classification comes from Candidate Master (Below $4500 / Above $4500).
- Inactive / incentive-excluded Candidate Master rows are excluded from slab counts
  and do not receive incentive.
- Eligible only after Start Date + 90 days.
- Recruiter slab uses placement count scoped by:
  Recruiter + Placement Month (from start date) + Finder Fee category.
  Below-$4500 and At/Above-$4500 counts are independent — never combined.
- If first payment received: pay remaining recruiter amount one-time after 90 days.
- If payment not received by 90 days: pay recruiter amount in equal 1/3 installments
  after 90 days (tracked via prior paid amounts).
- Hierarchy (TL, Manager, CRM, AD, Center Head): fixed one-time after 90 days;
  not subject to the recruiter 3-month installment rule.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Tuple

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

# Slab group key: (recruiter_lower, placement_month YYYY-MM, finder_fee_above)
FteSlabGroupKey = Tuple[str, str, bool]


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _finder_fees_raw(candidate: Candidate) -> str:
    raw = str(getattr(candidate, "finder_fees", None) or "")
    return (
        raw.strip()
        .upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace("$", "")
        .replace(",", "")
        .replace("₹", "")
        .replace("RS.", "")
        .replace("RS", "")
    )


def resolve_finder_fee_above(candidate: Candidate) -> Optional[bool]:
    """
    Classify finder-fee category for slab grouping.

    Returns:
      True  → At/Above ₹4,500
      False → Below ₹4,500
      None  → unset / unknown (excluded from slab counts)
    """
    raw = _finder_fees_raw(candidate)
    if raw in {"ABOVE500", "ABOVE4500"} or (
        raw.startswith("ABOVE") and any(ch.isdigit() for ch in raw)
    ):
        return True
    if raw in {"BELOW500", "BELOW4500"} or (
        raw.startswith("BELOW") and any(ch.isdigit() for ch in raw)
    ):
        return False

    # Fallback: numeric finders_fee amount on Candidate Master.
    numeric = getattr(candidate, "finders_fee", None)
    if numeric is not None:
        try:
            amount = Decimal(str(numeric))
            if amount > ZERO:
                return amount >= Decimal("4500")
        except Exception:
            pass
    return None


def finder_fee_is_set(candidate: Candidate) -> bool:
    """True when Candidate Master has a Below/Above finder-fee classification."""
    return resolve_finder_fee_above(candidate) is not None


def finder_fee_above_from_master(candidate: Candidate) -> bool:
    """True when Candidate Master Finder Fees is Above $4500."""
<<<<<<< Updated upstream
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
=======
    return resolve_finder_fee_above(candidate) is True
>>>>>>> Stashed changes


def finder_fee_label(candidate: Candidate) -> str:
    resolved = resolve_finder_fee_above(candidate)
    if resolved is True:
        return "Above $4500"
    if resolved is False:
        return "Below $4500"
    return "None"


def placement_month_from_start(
    start_date: Optional[date],
    *,
    fallback_month: str = "",
) -> str:
    """Placement month for FTE slab grouping — always from start date, not cycle month."""
    if start_date:
        return start_date.strftime("%Y-%m")
    return (fallback_month or "").strip()


def fte_slab_group_key(
    recruiter: Optional[str],
    placement_month: str,
    finder_fee_above: bool,
) -> FteSlabGroupKey:
    return (
        str(recruiter or "").strip().lower(),
        (placement_month or "").strip(),
        bool(finder_fee_above),
    )


def _is_incentive_active_candidate(candidate: Candidate) -> bool:
    """Inactive / excluded Candidate Master rows must not enter FTE slab counts."""
    if getattr(candidate, "incentive_active", True) is False:
        return False
    status = str(getattr(candidate, "status", "") or "").strip().upper()
    if status in {
        "INACTIVE",
        "INACTIVE (EXCLUDED)",
        "LEFT",
        "MARKED LEFT",
        "PROJECT ENDED",
        "NOT APPROVED INACTIVE",
    }:
        return False
    return True


def build_nashik_fte_slab_counts(
    candidates: Iterable[Candidate],
    *,
    fallback_month: str = "",
) -> Dict[FteSlabGroupKey, int]:
    """
    Count FTE placements per (recruiter, placement month, finder-fee category).

    Below-$4500 and At/Above-$4500 are independent groups. Candidates without a
    set finder-fee classification are excluded from slab counts.
    Inactive / incentive-excluded Candidate Master rows are also excluded.
    """
    counts: Counter[FteSlabGroupKey] = Counter()
    for cand in candidates:
        if not is_fte_contract(getattr(cand, "contract_type", None)):
            continue
        if not _is_incentive_active_candidate(cand):
            continue
        if not finder_fee_is_set(cand):
            continue
        month = placement_month_from_start(
            getattr(cand, "start_date", None),
            fallback_month=fallback_month,
        )
        fee_above = resolve_finder_fee_above(cand)
        assert fee_above is not None
        key = fte_slab_group_key(
            getattr(cand, "recruiter", None),
            month,
            fee_above,
        )
        counts[key] += 1
    return dict(counts)


def nashik_fte_placement_count_for_candidate(
    candidate: Candidate,
    slab_counts: Dict[FteSlabGroupKey, int],
    *,
    fallback_month: str = "",
) -> int:
    """Return this candidate's fee-category slab count (min 1 when fee is set)."""
    fee_above = resolve_finder_fee_above(candidate)
    if fee_above is None:
        return 1
    month = placement_month_from_start(
        getattr(candidate, "start_date", None),
        fallback_month=fallback_month,
    )
    key = fte_slab_group_key(
        getattr(candidate, "recruiter", None),
        month,
        fee_above,
    )
    return max(1, int(slab_counts.get(key, 1)))


def peer_fee_category_counts(
    candidate: Candidate,
    slab_counts: Dict[FteSlabGroupKey, int],
    *,
    fallback_month: str = "",
) -> Dict[str, int]:
    """Return below/above counts for the same recruiter + placement month (debug/audit)."""
    month = placement_month_from_start(
        getattr(candidate, "start_date", None),
        fallback_month=fallback_month,
    )
    recruiter = getattr(candidate, "recruiter", None)
    below_key = fte_slab_group_key(recruiter, month, False)
    above_key = fte_slab_group_key(recruiter, month, True)
    return {
        "below_4500_count": int(slab_counts.get(below_key, 0)),
        "above_4500_count": int(slab_counts.get(above_key, 0)),
    }


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
    fee_category_peer_counts: Optional[Dict[str, int]] = None,
) -> List[LineDraft]:
    """Calculate Nashik FTE incentive lines for one Candidate Master placement."""
    as_of = cycle_end or date.today()
    paid = payment_status.upper() in {"RECEIVED", "PAYMENT_RECEIVED", "NOT_APPLICABLE"}
    days_done = days_completed_from_start(c.start_date, as_of)
    eligible_on = ninety_day_eligible_date(c.start_date)
    days_gate_ok = days_done >= FTE_MIN_DAYS
    hours_proxy = Decimal(str(days_done))

    fee_resolved = resolve_finder_fee_above(c)
    fee_above = fee_resolved is True
    full_recruiter = Decimal(
        fte_recruiter_amount(fee_above, max(1, int(placement_count_this_month)))
    )

    hard_blocked = ""
    if cycle_end and c.start_date and c.start_date > cycle_end:
        hard_blocked = "NOT_YET_STARTED"
    elif not matches_nashik_company(c.candidate_source, c.organization):
        hard_blocked = "INVALID_SOURCE"
    elif not is_nashik_office(c.recruiter_location):
        hard_blocked = "INVALID_LOCATION"
    elif fee_resolved is None:
        hard_blocked = "FINDER_FEE_NOT_SET"

    coord_rec = lookup_coordinator(coordinators, c.recruiter)
    if coordinators and (c.recruiter or "").strip() and not coord_rec:
        recruiter_status = "MISSING"
    else:
        recruiter_status = getattr(coord_rec, "employment_status", "ACTIVE")
        recruiter_status = getattr(recruiter_status, "value", str(recruiter_status)).upper()

    peer = fee_category_peer_counts or {}
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
        "placement_month": placement_month_from_start(c.start_date),
        # Count used for THIS candidate's slab (fee-category scoped — never combined).
        "placement_count_this_month": placement_count_this_month,
        "slab_group": "ABOVE_4500" if fee_above else "BELOW_4500",
        "below_4500_count_same_recruiter_month": int(peer.get("below_4500_count", 0)),
        "above_4500_count_same_recruiter_month": int(peer.get("above_4500_count", 0)),
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
