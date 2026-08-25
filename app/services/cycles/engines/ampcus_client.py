"""Ampcus Tech Client incentive rules.

This engine deliberately has no hours or 90-day condition.  It consumes the
reviewed placement snapshot (Candidate in the current data model) and emits
server-calculated line drafts only.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.repositories.entities.candidate import Candidate
from app.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from app.services.cycles.recruiter_master import (
    EXEMPTED_MISSING_RECRUITER_MASTER,
    EXEMPTION_REASON_TEXT,
    lookup_coordinator,
)
from app.services.incentives.nashik_calculator import LineDraft

ZERO = Decimal("0")
ROLES = ("Recruiter", "Team Lead", "Manager", "CRM", "CH/VP")
SLABS: Tuple[Tuple[Decimal, Decimal, Dict[str, int]], ...] = (
    (Decimal("0"), Decimal("4.99"), {role: 0 for role in ROLES}),
    (Decimal("5"), Decimal("10"), {"Recruiter": 2000, "Team Lead": 250, "Manager": 500, "CRM": 750, "CH/VP": 500}),
    (Decimal("10.01"), Decimal("15"), {"Recruiter": 3000, "Team Lead": 250, "Manager": 500, "CRM": 750, "CH/VP": 1000}),
    (Decimal("15.01"), Decimal("20"), {"Recruiter": 5000, "Team Lead": 500, "Manager": 1000, "CRM": 1000, "CH/VP": 1500}),
    (Decimal("20.01"), Decimal("25"), {"Recruiter": 6000, "Team Lead": 500, "Manager": 1000, "CRM": 1500, "CH/VP": 2000}),
    (Decimal("25.01"), Decimal("30"), {"Recruiter": 7000, "Team Lead": 500, "Manager": 1000, "CRM": 1500, "CH/VP": 2500}),
    (Decimal("30.01"), Decimal("35"), {"Recruiter": 8000, "Team Lead": 500, "Manager": 1000, "CRM": 1500, "CH/VP": 3000}),
    (Decimal("35.01"), Decimal("40"), {"Recruiter": 9000, "Team Lead": 500, "Manager": 1000, "CRM": 1500, "CH/VP": 3500}),
    (Decimal("40.01"), Decimal("100"), {"Recruiter": 10000, "Team Lead": 500, "Manager": 1000, "CRM": 1500, "CH/VP": 4000}),
)


def is_ampcus_client_division(division: Optional[str]) -> bool:
    return str(division or "").strip().lower().replace(" ", "").replace("-", "") in {
        "ampcustechclient", "ampcustech(client)", "ampcusclient"
    }


def _is_not_applicable(person: Optional[str]) -> bool:
    if not person:
        return False
    norm = str(person).strip().lower().replace(" ", "").replace("/", "").replace("-", "").replace(".", "")
    return norm in {"na", "notapplicable", "none", ""}


def normalize_person(value: Optional[str]) -> str:
    return " ".join((value or "").split()).strip().lower()


def resolve_slab(markup: Optional[Decimal]) -> Optional[Tuple[Decimal, Decimal, Dict[str, int]]]:
    if markup is None or markup < ZERO or markup > Decimal("100"):
        return None
    
    # Quantize to 2 decimal places to align with slab definitions
    markup = markup.quantize(Decimal("0.01"))
    
    for low, high, amounts in SLABS:
        if low <= markup <= high:
            return low, high, amounts
    return None


def _line(candidate: Candidate, role: str, person: Optional[str], amount: Decimal, *, eligible: bool, reason: str, rule: str, details: dict) -> LineDraft:
    return LineDraft(
        candidate_id=candidate.id,
        candidate_name=candidate.candidate_name,
        role=role,
        person=(person or "—").strip(),
        incentive_type="AMPCUS_CLIENT_MARKUP",
        rule_applied=rule,
        eligible=eligible,
        base_incentive=amount,
        pro_rata_factor=Decimal("1") if eligible else ZERO,
        amount=amount if eligible else ZERO,
        hours=ZERO,
        margin=candidate.margin,
        reason=reason,
        explanation=[json.dumps(details, default=str)],
    )


def _people(candidate: Candidate) -> Dict[str, Optional[str]]:
    # CH takes precedence over AVP/VP.  The slab is paid exactly once.
    return {
        "Recruiter": candidate.recruiter,
        "Team Lead": candidate.team_lead,
        "Manager": candidate.manager,
        "CRM": candidate.crm,
        "CH/VP": candidate.center_head or candidate.avp,
    }


def _inactive(candidate: Candidate) -> bool:
    return candidate.incentive_active is False or "INACTIVE" in str(candidate.status or "").upper()


def _project_ended(candidate: Candidate, cycle_end: date) -> bool:
    return candidate.end_date is not None and candidate.end_date <= cycle_end


def calculate_placement(
    candidate: Candidate,
    *, cycle_end: date,
    payment: Optional[object] = None,
    coordinators: Optional[Dict[str, CoordinatorRecord]] = None,
    paid_keys: Optional[Set[str]] = None,
) -> List[LineDraft]:
    """Return five deterministic role lines for one placement snapshot."""
    people = _people(candidate)
    markup = candidate.margin
    payment_status = str(getattr(payment, "status", "PAYMENT_PENDING") or "PAYMENT_PENDING").upper()
    details = {
        "margin": str(markup) if markup is not None else None,
        "payment_status": payment_status,
        "payment_received_date": str(getattr(payment, "payment_received_date", None) or "") or None,
        "payment_reference": getattr(payment, "payment_reference", None),
        "ownership_confirmed": getattr(candidate, "ownership_confirmed", False),
        "start_date": getattr(candidate, "start_date", None).isoformat() if getattr(candidate, "start_date", None) else None,
        "end_date": getattr(candidate, "end_date", None).isoformat() if getattr(candidate, "end_date", None) else None,
        "project_ended": _project_ended(candidate, cycle_end),
        "contract_type": getattr(candidate, "contract_type", None),
        "candidate_source": getattr(candidate, "candidate_source", None) or getattr(candidate, "organization", None),
        "candidate_id": getattr(candidate, "start_id", None) or getattr(candidate, "external_candidate_id", None) or str(candidate.id),
        "external_candidate_id": getattr(candidate, "external_candidate_id", None),
        "recruiter": getattr(candidate, "recruiter", None),
        "team_lead": getattr(candidate, "team_lead", None),
        "manager": getattr(candidate, "manager", None),
        "crm": getattr(candidate, "crm", None),
        "center_head": getattr(candidate, "center_head", None),
        "avp": getattr(candidate, "avp", None),
    }
    def all_zero(reason: str, rule: str) -> List[LineDraft]:
        return [_line(candidate, role, people[role], ZERO, eligible=False, reason=reason, rule=rule, details=details) for role in ROLES]

    if not candidate.start_date:
        return all_zero("CANDIDATE_NOT_STARTED", "Ampcus Client eligibility")
    ownership_ok = candidate.ownership_confirmed or bool(
        candidate.recruiter and str(candidate.recruiter).strip()
    )
    if not ownership_ok:
        return all_zero("OWNERSHIP_NOT_CONFIRMED", "Ampcus Client eligibility")
    if _inactive(candidate):
        return all_zero("CANDIDATE_INACTIVE", "Ampcus Client eligibility")
    if _project_ended(candidate, cycle_end):
        return all_zero("PROJECT_ENDED", "Ampcus Client eligibility")
    if payment_status not in {"RECEIVED", "PAYMENT_RECEIVED"}:
        return all_zero("PAYMENT_PENDING", "Ampcus Client payment gate")
    slab = resolve_slab(markup)
    if slab is None:
        return all_zero("MARKUP_NOT_AVAILABLE" if markup is None else "MARKUP_OUT_OF_RANGE", "Ampcus Client mark-up validation")
    low, high, amounts = slab
    details["incentive_slab"] = {"min_markup": str(low), "max_markup": str(high)}
    if low == ZERO:
        return all_zero("MARKUP_BELOW_INCENTIVE_THRESHOLD", "Ampcus Client mark-up slab")

    coordinators = coordinators or {}
    paid_keys = paid_keys or set()
    
    # Enforce max-two-roles for all roles
    ROLE_PRIORITY = ["Recruiter", "CH/VP", "CRM", "Manager", "Team Lead"]
    
    by_person: Dict[str, List[str]] = {}
    for role in ROLES:
        person = people[role]
        if person and not _is_not_applicable(person):
            norm = normalize_person(person)
            by_person.setdefault(norm, []).append(role)
            
    allowed_roles = set()
    for norm_name, roles_held in by_person.items():
        if len(roles_held) <= 2:
            allowed_roles.update(roles_held)
        else:
            # Keep top 2 priority roles
            ordered = sorted(roles_held, key=lambda r: ROLE_PRIORITY.index(r))
            allowed_roles.update(ordered[:2])

    lines: List[LineDraft] = []
    for role in ROLES:
        person = people[role]
        amount = Decimal(amounts[role])
        
        # 1. Missing Hierarchy Check (Per-Role)
        if not person or not str(person).strip():
            lines.append(
                _line(
                    candidate,
                    role,
                    person,
                    ZERO,
                    eligible=False,
                    reason="MISSING_HIERARCHY",
                    rule="Ampcus Client hierarchy validation",
                    details=details,
                )
            )
            continue
            
        # 2. Not Applicable Check
        if _is_not_applicable(person):
            lines.append(
                _line(
                    candidate,
                    role,
                    person,
                    ZERO,
                    eligible=False,
                    reason="ROLE_NOT_APPLICABLE",
                    rule="Ampcus Client hierarchy validation",
                    details=details,
                )
            )
            continue

        # 3. Already Paid Check
        person_clean = person.strip().lower()
        key = f"{candidate.id}|AMPCUS_CLIENT_MARKUP|{role}|{person_clean}"
        if key in paid_keys:
            lines.append(
                _line(
                    candidate,
                    role,
                    person,
                    ZERO,
                    eligible=False,
                    reason="ALREADY_PAID",
                    rule="Ampcus Client duplicate payment prevention",
                    details=details,
                )
            )
            continue

        # 4. Max Two Roles Enforced
        if role not in allowed_roles:
            lines.append(
                _line(
                    candidate,
                    role,
                    person,
                    ZERO,
                    eligible=False,
                    reason="ROLE_LIMIT_EXCEEDED",
                    rule="Ampcus Client role limit enforcement",
                    details=details,
                )
            )
            continue
            
        coord = lookup_coordinator(coordinators, person)
        # No Recruiter Master uploaded at all -> skip the presence exemption entirely.
        if coordinators and not coord:
            lines.append(
                _line(
                    candidate,
                    role,
                    person,
                    ZERO,
                    eligible=False,
                    reason=EXEMPTED_MISSING_RECRUITER_MASTER,
                    rule="Ampcus Client Recruiter Master presence",
                    details={**details, "exemption": EXEMPTION_REASON_TEXT},
                )
            )
            continue
        coordinator_status = getattr(coord, "employment_status", CoordinatorStatus.ACTIVE)
        coordinator_status_value = getattr(coordinator_status, "value", str(coordinator_status)).upper()
        if coordinator_status_value in {CoordinatorStatus.LEFT.value, CoordinatorStatus.NOTICE.value}:
            reason = (
                "COORDINATOR_LEFT"
                if coordinator_status_value == CoordinatorStatus.LEFT.value
                else "COORDINATOR_ON_NOTICE"
            )
            lines.append(
                _line(
                    candidate,
                    role,
                    person,
                    ZERO,
                    eligible=False,
                    reason=reason,
                    rule="Ampcus Client coordinator status",
                    details={**details, "coordinator_status": coordinator_status_value},
                )
            )
        else:
            lines.append(
                _line(
                    candidate,
                    role,
                    person,
                    amount,
                    eligible=True,
                    reason="ELIGIBLE",
                    rule=f"Ampcus Client mark-up {low}–{high}%",
                    details={**details, "coordinator_status": coordinator_status_value},
                )
            )
    return lines


def coordinator_index(db: Session) -> Dict[str, CoordinatorRecord]:
    """Index every non-deleted Recruiter Master row. LEFT / NOTICE / Inactive still count as present."""
    out: Dict[str, CoordinatorRecord] = {}
    rows = (
        db.query(CoordinatorRecord)
        .filter(CoordinatorRecord.is_deleted.is_(False))
        .all()
    )
    for row in rows:
        for raw in (row.normalized_name, row.full_name, row.email):
            key = normalize_person(raw)
            if key:
                out[key] = row
    return out
