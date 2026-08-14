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


def _hierarchy(p: PlacementInput) -> List[Tuple[str, str]]:
    raw = [
        ("Team Lead", p.team_lead),
        ("Manager", p.manager),
        ("Senior Manager", p.senior_manager),
        ("CRM", p.crm),
        ("Associate Director", p.associate_director),
        ("Center Head", p.center_head),
        ("AVP", p.avp),
    ]
    return [(role, person.strip()) for role, person in raw if person and person.strip()]


def _limit_roles(entries: Sequence[Tuple[str, str]], max_roles: int) -> List[Tuple[str, str]]:
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


def calculate_nashik_placement(
    p: PlacementInput,
    window: CycleWindow,
    paid_keys: Optional[Set[str]] = None,
) -> List[LineDraft]:
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

    mapped = [
        (role, person)
        for role, person in _hierarchy(p)
        if role == "Team Lead" or role in LEADERSHIP_ONE_TIME
    ]
    selected = _limit_roles(mapped, MAX_ROLES_PER_PERSON)
    selected_summary = "; ".join(f"{role}={person}" for role, person in selected) or "none"
    lines: List[LineDraft] = []

    if p.project_ended and hours < STANDARD_HOURS:
        lines.append(
            _line(
                p,
                role="Recruiter",
                person=p.recruiter or "—",
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
                ],
            )
        )
        for role, person in selected:
            if role == "Team Lead":
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
                        explanation=["Nashik project-end rule sets Team Lead to ₹0"],
                    )
                )
        return _apply_duplicates(lines, paid_keys)

    if p.margin is not None:
        kind, base, category = nashik_recruiter_base(p.margin)
        if kind == "special":
            lines.append(
                _line(
                    p,
                    role="Recruiter",
                    person=p.recruiter or "—",
                    incentive_type="SPECIAL",
                    rule_applied="Nashik — Margin ≤ $0.99 special one-time",
                    eligible=True,
                    base=base,
                    factor=Decimal("1"),
                    amount=base,
                    reason="Low margin special incentive per successful placement",
                    explanation=[
                        "Incentive Type = Recruiter Special One-Time",
                        f"Margin Category = {category}",
                        f"Approved margin/hour = ${p.margin}",
                        f"Base Incentive = {_inr(base)}",
                        "One-time only — duplicate ledger blocks a second payment",
                    ],
                )
            )
        else:
            factor, amount = nashik_pro_rata(base, hours)
            lines.append(
                _line(
                    p,
                    role="Recruiter",
                    person=p.recruiter or "—",
                    incentive_type="RECURRING",
                    rule_applied="Nashik Recruiter Recurring (margin/hour slab)",
                    eligible=base > 0,
                    base=base,
                    factor=factor,
                    amount=amount,
                    reason=(
                        "Margin falls outside the configured slabs"
                        if base == 0
                        else "Full incentive — 160+ hours completed"
                        if hours >= STANDARD_HOURS
                        else "Pro-rata incentive for hours below 160"
                    ),
                    explanation=[
                        f"Candidate → Division Nashik → Contract {normalize_contract(p.contract_type)}",
                        f"Hours = {hours} · Approved margin/hour = ${p.margin}",
                        f"Applicable Incentive Slab = {category}",
                        f"Base Incentive = {_inr(base)}",
                        f"Pro-Rata Factor = {hours} / {STANDARD_HOURS} = {factor}",
                        f"Final Incentive = {_inr(amount)}",
                    ],
                )
            )

    for role, person in selected:
        if role == "Team Lead":
            factor, amount = nashik_pro_rata(TEAM_LEAD_BASE, hours)
            lines.append(
                _line(
                    p,
                    role="Team Lead",
                    person=person,
                    incentive_type="RECURRING",
                    rule_applied="Nashik Team Lead Recurring",
                    eligible=True,
                    base=TEAM_LEAD_BASE,
                    factor=factor,
                    amount=amount,
                    reason="Full ₹250 for 160 hours" if hours >= STANDARD_HOURS else "Pro-rata for hours below 160",
                    explanation=[
                        f"Person = {person} · Role = Team Lead · Recurring",
                        f"{_inr(TEAM_LEAD_BASE)} × {hours} / {STANDARD_HOURS} = {_inr(amount)}",
                        f"Selected roles (max {MAX_ROLES_PER_PERSON} per person): {selected_summary}",
                    ],
                )
            )
            continue
        amount = LEADERSHIP_ONE_TIME[role]
        eligible = hours >= STANDARD_HOURS
        lines.append(
            _line(
                p,
                role=role,
                person=person,
                incentive_type="ONE_TIME",
                rule_applied=f"Nashik Division — Leadership one-time ({role})",
                eligible=eligible,
                base=amount,
                factor=Decimal("1"),
                amount=amount,
                reason=(
                    "Candidate completed 160 hours — one-time leadership incentive"
                    if eligible
                    else f"Only {hours} hours completed — 160 hours required (not pro-rated)"
                ),
                explanation=[
                    f"Person = {person} · Role = {role} · One-Time",
                    f"160-hour requirement = {STANDARD_HOURS} · Hours completed = {hours}",
                    f"One-time amount {_inr(amount)} (not pro-rated)",
                    "Previous payment check via approved-cycle history",
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
) -> List[LineDraft]:
    lines: List[LineDraft] = []
    for placement in placements:
        lines.extend(calculate_nashik_placement(placement, window, paid_keys))
    return lines
