"""Nashik placement calculator used by the existing Division Incentive Cycle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.services.incentives.nashik_rules import (
    LEADERSHIP_ONE_TIME,
    MAX_ROLES_PER_PERSON,
    NASHIK_CONTRACT_TYPES,
    PROJECT_END_RECRUITER,
    ROLE_PRIORITY,
    STANDARD_HOURS,
    TEAM_LEAD_BASE,
    is_nashik_office,
    matches_nashik_company,
    money,
    nashik_pro_rata,
    nashik_recruiter_base,
    normalize_contract,
    normalize_person,
)
from app.services.incentives.recruiter_master import (
    EXEMPTED_MISSING_RECRUITER_MASTER,
    EXEMPTION_REASON_TEXT,
)

# Employment statuses that block incentive for a person (mirrors Client/Sambhaji).
INELIGIBLE_EMPLOYMENT_STATUSES = {"LEFT", "NOTICE"}


@dataclass
class PlacementInput:
    candidate_pk: int
    external_id: str
    name: str
    contract_type: Optional[str]
    candidate_source: Optional[str]
    organization: Optional[str]
    recruiter_location: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    margin: Optional[Decimal]
    hours: Decimal
    recruiter: Optional[str]
    team_lead: Optional[str]
    crm: Optional[str]
    manager: Optional[str]
    senior_manager: Optional[str]
    associate_director: Optional[str]
    center_head: Optional[str]
    avp: Optional[str]
    director: Optional[str] = None
    incentive_active: bool = True
    project_ended: bool = False


@dataclass
class CycleWindow:
    start: date
    end: date


@dataclass
class LineDraft:
    candidate_id: Optional[int]
    candidate_name: str
    role: str
    person: str
    incentive_type: str
    rule_applied: str
    eligible: bool
    base_incentive: Decimal
    pro_rata_factor: Decimal
    amount: Decimal
    hours: Decimal
    margin: Optional[Decimal]
    reason: str
    explanation: List[str] = field(default_factory=list)

    def explanation_json(self) -> str:
        if self.explanation and str(self.explanation[0]).lstrip().startswith("{"):
            return str(self.explanation[0])
        return json.dumps(self.explanation)

    def paid_key(self) -> str:
        return "|".join(
            [
                str(self.candidate_id or ""),
                self.incentive_type,
                self.role,
                normalize_person(self.person),
            ]
        )


def _inr(value: Decimal) -> str:
    return f"₹{int(money(value)):,}"


def _all_roles(p: PlacementInput) -> List[Tuple[str, str]]:
    """Collect every occupied role including Recruiter (dedupe same role)."""
    raw = [
        ("Recruiter", p.recruiter),
        ("Team Lead", p.team_lead),
        ("Manager", p.manager),
        ("Senior Manager", p.senior_manager),
        ("CRM", p.crm),
        ("Associate Director", p.associate_director),
        ("Center Head", p.center_head),
        ("AVP", p.avp),
        ("Director", p.director),
    ]
    seen_roles: Set[str] = set()
    out: List[Tuple[str, str]] = []
    for role, person in raw:
        if not person or not str(person).strip():
            continue
        if role in seen_roles:
            continue
        seen_roles.add(role)
        out.append((role, str(person).strip()))
    return out


def _employment_status(
    person: str,
    employment_status: Optional[Dict[str, str]],
    role: Optional[str] = None,
) -> str:
    """
    Resolve ACTIVE|LEFT|NOTICE|MISSING for a hierarchy participant.

    When employment_status is None or empty (no Recruiter Master uploaded),
    keep the historical default of ACTIVE — nobody is exempted.
    When a non-empty snapshot is provided, a person with no row is MISSING (not ACTIVE).
    LEFT / NOTICE / Inactive rows in Recruiter Master still count as present.
    """
    if not employment_status:
        return "ACTIVE"
    key = normalize_person(person)
    if role:
        role_key = f"{role.strip().lower()}|{key}"
        if role_key in employment_status:
            return str(employment_status[role_key] or "ACTIVE").upper()
    if key not in employment_status:
        return "MISSING"
    return str(employment_status.get(key, "ACTIVE") or "ACTIVE").upper()


def _status_reason(status: str) -> str:
    if status == "LEFT":
        return "COORDINATOR_LEFT"
    if status == "NOTICE":
        return "COORDINATOR_ON_NOTICE"
    return "COORDINATOR_INELIGIBLE"


def _limit_roles(entries: Sequence[Tuple[str, str]], max_roles: int) -> List[Tuple[str, str]]:
    """Per-person top-N by ROLE_PRIORITY (includes Recruiter)."""
    by_person: Dict[str, List[Tuple[str, str]]] = {}
    for role, person in entries:
        by_person.setdefault(normalize_person(person), []).append((role, person))
    out: List[Tuple[str, str]] = []
    for group in by_person.values():
        ordered = sorted(
            group,
            key=lambda item: ROLE_PRIORITY.index(item[0]) if item[0] in ROLE_PRIORITY else 99,
        )
        out.extend(ordered[:max_roles])
    return out


def _overlaps(p: PlacementInput, window: CycleWindow) -> bool:
    if p.start_date and p.start_date > window.end:
        return False
    if p.end_date and p.end_date < window.start:
        return False
    return True


def _line(
    p: PlacementInput,
    *,
    role: str,
    person: str,
    incentive_type: str,
    rule_applied: str,
    eligible: bool,
    base: Decimal,
    factor: Decimal,
    amount: Decimal,
    reason: str,
    explanation: List[str],
) -> LineDraft:
    return LineDraft(
        candidate_id=p.candidate_pk,
        candidate_name=p.name,
        role=role,
        person=person or "—",
        incentive_type=incentive_type,
        rule_applied=rule_applied,
        eligible=eligible,
        base_incentive=money(base),
        pro_rata_factor=factor,
        amount=money(amount) if eligible else Decimal("0"),
        hours=money(p.hours),
        margin=money(p.margin) if p.margin is not None else None,
        reason=reason,
        explanation=explanation,
    )


def _scope(p: PlacementInput, reason: str, explanation: List[str]) -> List[LineDraft]:
    return [
        _line(
            p,
            role="Recruiter",
            person=p.recruiter or "—",
            incentive_type="RECURRING",
            rule_applied="Nashik placement scope",
            eligible=False,
            base=Decimal("0"),
            factor=Decimal("0"),
            amount=Decimal("0"),
            reason=reason,
            explanation=explanation,
        )
    ]


def _role_amount(
    p: PlacementInput,
    role: str,
    hours: Decimal,
) -> Tuple[str, Decimal, Decimal, Decimal, str, List[str]]:
    """
    Return (incentive_type, base, factor, amount, reason, explanation) for a selected role.
    Eligibility against hours is applied by the caller after status/top-2 selection.
    """
    if role == "Recruiter":
        if p.margin is None:
            return (
                "RECURRING",
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                "Margin is required for Nashik recruiter incentive",
                ["Approved margin/hour is missing"],
            )
        kind, base, category = nashik_recruiter_base(p.margin)
        if kind == "special":
            return (
                "SPECIAL",
                base,
                Decimal("1"),
                base,
                "Low margin special incentive per successful placement",
                [
                    "Incentive Type = Recruiter Special One-Time",
                    f"Margin Category = {category}",
                    f"Approved margin/hour = ${p.margin}",
                    f"Base Incentive = {_inr(base)}",
                    "One-time only — duplicate ledger blocks a second payment",
                ],
            )
        factor, amount = nashik_pro_rata(base, hours)
        reason = (
            "Margin falls outside the configured slabs"
            if base == 0
            else "Full incentive — 160+ hours completed"
            if hours >= STANDARD_HOURS
            else "Pro-rata incentive for hours below 160"
        )
        return (
            "RECURRING",
            base,
            factor,
            amount,
            reason,
            [
                f"Candidate → Division Nashik → Contract {normalize_contract(p.contract_type)}",
                f"Hours = {hours} · Approved margin/hour = ${p.margin}",
                f"Applicable Incentive Slab = {category}",
                f"Base Incentive = {_inr(base)}",
                f"Pro-Rata Factor = {hours} / {STANDARD_HOURS} = {factor}",
                f"Final Incentive = {_inr(amount)}",
            ],
        )

    if role == "Team Lead":
        factor, amount = nashik_pro_rata(TEAM_LEAD_BASE, hours)
        return (
            "RECURRING",
            TEAM_LEAD_BASE,
            factor,
            amount,
            "Full ₹250 for 160 hours" if hours >= STANDARD_HOURS else "Pro-rata for hours below 160",
            [
                f"Person role = Team Lead · Recurring",
                f"{_inr(TEAM_LEAD_BASE)} × {hours} / {STANDARD_HOURS} = {_inr(amount)}",
            ],
        )

    amount = LEADERSHIP_ONE_TIME[role]
    return (
        "ONE_TIME",
        amount,
        Decimal("1"),
        amount,
        (
            "Candidate completed 160 hours — one-time leadership incentive"
            if hours >= STANDARD_HOURS
            else f"Only {hours} hours completed — 160 hours required (not pro-rated)"
        ),
        [
            f"Person role = {role} · One-Time",
            f"160-hour requirement = {STANDARD_HOURS} · Hours completed = {hours}",
            f"One-time amount {_inr(amount)} (not pro-rated)",
            "Previous payment check via approved-cycle history",
        ],
    )


def calculate_nashik_placement(
    p: PlacementInput,
    window: CycleWindow,
    paid_keys: Optional[Set[str]] = None,
    employment_status: Optional[Dict[str, str]] = None,
) -> List[LineDraft]:
    """
    employment_status: map of normalize_person(name) -> ACTIVE|LEFT|NOTICE
    sourced from Coordinator Master via cycle_engine.coordinator_index.
    """
    paid_keys = paid_keys or set()
    hours = p.hours if p.hours is not None else Decimal("0")
    p.hours = hours

    if not p.incentive_active:
        return _scope(p, "Candidate is marked incentive-inactive", [
            "Existing candidate/project status excludes this placement from Nashik calculation",
        ])
    if normalize_contract(p.contract_type) not in NASHIK_CONTRACT_TYPES:
        return _scope(
            p,
            f"Nashik W2/C2C rules do not apply to {p.contract_type or 'unknown'} placements",
            ["Nashik recurring/leadership formulas apply only to W2 and C2C"],
        )
    if not matches_nashik_company(p.candidate_source, p.organization):
        return _scope(p, "Company is outside Nashik rule sources", [
            f"Source/organization: {p.candidate_source or p.organization or '—'}",
        ])
    if not is_nashik_office(p.recruiter_location):
        return _scope(p, "Placement does not originate from Nashik Office", [
            f"Recruiter location: {p.recruiter_location}",
        ])
    if not _overlaps(p, window):
        return _scope(p, "Placement is outside the incentive cycle period", [
            f"Candidate start {p.start_date} · project end {p.end_date}",
            f"Cycle {window.start} to {window.end}",
        ])

    occupied = _all_roles(p)
    if not occupied:
        return _scope(p, "No hierarchy or recruiter assigned", ["No roles available for calculation"])

    configured_roles = {"Recruiter", "Team Lead"} | set(LEADERSHIP_ONE_TIME)

    # 1) Recruiter Master presence, then LEFT/NOTICE. Missing people do not compete for top-2.
    missing_blocked: List[Tuple[str, str]] = []
    status_blocked: List[Tuple[str, str, str]] = []
    status_ok: List[Tuple[str, str]] = []
    for role, person in occupied:
        status = _employment_status(person, employment_status, role=role)
        if status == "MISSING":
            missing_blocked.append((role, person))
        elif status in INELIGIBLE_EMPLOYMENT_STATUSES:
            status_blocked.append((role, person, status))
        elif role in configured_roles:
            status_ok.append((role, person))

    # 2) Top-2 across ALL remaining roles (Recruiter included in the pool).
    selected = _limit_roles(status_ok, MAX_ROLES_PER_PERSON)
    selected_keys = {(role, normalize_person(person)) for role, person in selected}
    selected_summary = "; ".join(f"{role}={person}" for role, person in selected) or "none"

    lines: List[LineDraft] = []

    for role, person in missing_blocked:
        if role in configured_roles:
            incentive_type, base, factor, _amount, _reason, explanation = _role_amount(p, role, hours)
        else:
            incentive_type, base, factor, explanation = "ONE_TIME", Decimal("0"), Decimal("0"), []
        lines.append(
            _line(
                p,
                role=role,
                person=person,
                incentive_type=incentive_type,
                rule_applied="Nashik — Recruiter Master presence",
                eligible=False,
                base=base,
                factor=factor,
                amount=Decimal("0"),
                reason=EXEMPTED_MISSING_RECRUITER_MASTER,
                explanation=[
                    *explanation,
                    EXEMPTION_REASON_TEXT,
                    "Only this role is exempted; other hierarchy members continue",
                    f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                ],
            )
        )

    # Emit excluded LEFT/NOTICE lines (hierarchy continues for others).
    for role, person, status in status_blocked:
        if role not in configured_roles:
            continue
        incentive_type, base, factor, _amount, _reason, explanation = _role_amount(p, role, hours)
        lines.append(
            _line(
                p,
                role=role,
                person=person,
                incentive_type=incentive_type,
                rule_applied="Nashik — employment status exclusion",
                eligible=False,
                base=base,
                factor=factor,
                amount=Decimal("0"),
                reason=_status_reason(status),
                explanation=[
                    *explanation,
                    f"Employment status = {status}",
                    "LEFT/NOTICE employees are excluded from Nashik incentive",
                    "Remaining hierarchy continues for other eligible people",
                    f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                ],
            )
        )

    # Emit not-selected status-ok roles (lost top-2 competition).
    for role, person in status_ok:
        if (role, normalize_person(person)) in selected_keys:
            continue
        incentive_type, base, factor, _amount, _reason, explanation = _role_amount(p, role, hours)
        lines.append(
            _line(
                p,
                role=role,
                person=person,
                incentive_type=incentive_type,
                rule_applied="Nashik — max two roles per person",
                eligible=False,
                base=base,
                factor=factor,
                amount=Decimal("0"),
                reason="Role not selected under maximum two eligible roles rule",
                explanation=[
                    *explanation,
                    f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                ],
            )
        )

    # Project-end special: only recruiter flat amount when selected; TL forced to zero.
    if p.project_ended and hours < STANDARD_HOURS:
        for role, person in selected:
            if role == "Recruiter":
                lines.append(
                    _line(
                        p,
                        role="Recruiter",
                        person=person,
                        incentive_type="SPECIAL",
                        rule_applied="Nashik — Project end before 160 hours",
                        eligible=True,
                        base=PROJECT_END_RECRUITER,
                        factor=Decimal("1"),
                        amount=PROJECT_END_RECRUITER,
                        reason="Project ended before 160 hours — flat ₹2,000",
                        explanation=[
                            f"Project ended with {hours} hours worked (< 160)",
                            "Nashik rule: regular incentive is not processed",
                            f"Recruiter flat incentive = {_inr(PROJECT_END_RECRUITER)}",
                            f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                        ],
                    )
                )
            elif role == "Team Lead":
                lines.append(
                    _line(
                        p,
                        role="Team Lead",
                        person=person,
                        incentive_type="RECURRING",
                        rule_applied="Nashik — Project end before 160 hours",
                        eligible=False,
                        base=Decimal("0"),
                        factor=Decimal("0"),
                        amount=Decimal("0"),
                        reason="Project ended before 160 hours — Team Lead incentive is ₹0 for Nashik",
                        explanation=[
                            "Nashik project-end rule sets Team Lead to ₹0",
                            f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                        ],
                    )
                )
            else:
                incentive_type, base, factor, amount, reason, explanation = _role_amount(p, role, hours)
                lines.append(
                    _line(
                        p,
                        role=role,
                        person=person,
                        incentive_type=incentive_type,
                        rule_applied="Nashik — Project end before 160 hours",
                        eligible=False,
                        base=base,
                        factor=factor,
                        amount=Decimal("0"),
                        reason="Project ended before 160 hours — one-time incentive not payable",
                        explanation=[
                            *explanation,
                            f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                        ],
                    )
                )
        return _apply_duplicates(lines, paid_keys)

    # Normal path for selected roles.
    for role, person in selected:
        incentive_type, base, factor, amount, reason, explanation = _role_amount(p, role, hours)
        if role in LEADERSHIP_ONE_TIME and hours < STANDARD_HOURS:
            eligible = False
        elif role == "Recruiter" and base == 0 and incentive_type == "RECURRING":
            eligible = False
        else:
            eligible = True
        lines.append(
            _line(
                p,
                role=role,
                person=person,
                incentive_type=incentive_type,
                rule_applied=(
                    "Nashik Recruiter Recurring (margin/hour slab)"
                    if role == "Recruiter" and incentive_type == "RECURRING"
                    else "Nashik — Margin ≤ $0.99 special one-time"
                    if role == "Recruiter" and incentive_type == "SPECIAL"
                    else "Nashik Team Lead Recurring"
                    if role == "Team Lead"
                    else f"Nashik Division — Leadership one-time ({role})"
                ),
                eligible=eligible,
                base=base,
                factor=factor,
                amount=amount if eligible else Decimal("0"),
                reason=reason,
                explanation=[
                    *explanation,
                    f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                ],
            )
        )

    return _apply_duplicates(lines, paid_keys)


def _apply_duplicates(lines: Iterable[LineDraft], paid_keys: Set[str]) -> List[LineDraft]:
    seen: Set[str] = set()
    out: List[LineDraft] = []
    for line in lines:
        if line.incentive_type == "RECURRING" or not line.eligible:
            out.append(line)
            continue
        key = line.paid_key()
        if key in paid_keys or key in seen:
            line.eligible = False
            line.amount = Decimal("0")
            line.reason = "Duplicate — this one-time incentive was already paid in a previous cycle"
            line.explanation = [*line.explanation, "Blocked by duplicate incentive history"]
            out.append(line)
            continue
        seen.add(key)
        out.append(line)
    return out


def calculate_nashik_cycle(
    placements: Sequence[PlacementInput],
    window: CycleWindow,
    paid_keys: Optional[Set[str]] = None,
    employment_status: Optional[Dict[str, str]] = None,
) -> List[LineDraft]:
    lines: List[LineDraft] = []
    for placement in placements:
        lines.extend(
            calculate_nashik_placement(
                placement,
                window,
                paid_keys,
                employment_status=employment_status,
            )
        )
    return lines
