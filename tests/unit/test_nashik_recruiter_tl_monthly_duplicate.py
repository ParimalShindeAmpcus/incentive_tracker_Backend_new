"""
Nashik Recruiter and Team Lead: recurring across months, unique within a month.

Uniqueness: candidate + role + incentive_month (Nashik only).
Leadership one-time duplicate behavior is unchanged.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.entities.candidate import Candidate, CandidateDataVersion
from app.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from app.repositories.entities.cycle import CycleStatus, IncentiveCycle
from app.repositories.incentives import incentive_repository
from app.services.cycles.cycle_engine import run_cycle_calculation
from app.services.cycles.hours_name_matcher import HoursMatchRow
from app.services.incentives.nashik_calculator import CycleWindow
from app.services.incentives.nashik_rules import TEAM_LEAD_BASE, nashik_pro_rata, normalize_person

HIERARCHY = {
    "Recruiter": "TEST_RECRUITER_001",
    "Team Lead": "TEST_TL_001",
    "Manager": "TEST_MANAGER_001",
    "CRM": "TEST_CRM_001",
}


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _window(year: int, month: int) -> CycleWindow:
    import calendar

    last = calendar.monthrange(year, month)[1]
    return CycleWindow(start=date(year, month, 1), end=date(year, month, last))


def _seed_candidate(db, *, external_id: str, name: str) -> Candidate:
    version = CandidateDataVersion(version_label=f"v-{external_id}", division="nashik")
    db.add(version)
    db.flush()
    cand = Candidate(
        external_candidate_id=external_id,
        start_id=external_id,
        candidate_name=name,
        normalized_name=name.lower(),
        contract_type="C2C",
        margin=Decimal("8"),
        recruiter=HIERARCHY["Recruiter"],
        team_lead=HIERARCHY["Team Lead"],
        manager=HIERARCHY["Manager"],
        crm=HIERARCHY["CRM"],
        organization="Ampcus Inc",
        candidate_source="Ampcus Inc",
        recruiter_location="Nashik",
        start_date=date(2026, 1, 1),
        division="nashik",
        source_version_id=version.id,
        last_touched_version_id=version.id,
        incentive_active=True,
        is_active=True,
        status="ACTIVE",
    )
    db.add(cand)
    db.flush()
    return cand


def _seed_coordinators(db) -> None:
    for role, name in HIERARCHY.items():
        db.add(
            CoordinatorRecord(
                full_name=name,
                normalized_name=normalize_person(name),
                email=f"{name.lower()}@nashik-qa.example.com",
                organization="Ampcus Inc",
                role_title=role,
                employment_status=CoordinatorStatus.ACTIVE,
                incentive_eligible=True,
                is_deleted=False,
            )
        )
    db.flush()


def _cycle(db, month_key: str, *, division: str = "nashik") -> IncentiveCycle:
    year, month = (int(p) for p in month_key.split("-"))
    window = _window(year, month)
    cycle = IncentiveCycle(
        name=f"{division} {month_key}",
        division=division,
        incentive_month=month_key,
        cycle_start_date=window.start,
        cycle_end_date=window.end,
        status=CycleStatus.DRAFT,
    )
    db.add(cycle)
    db.flush()
    return cycle


def _hours_row(name: str, external_id: str, hours: float) -> HoursMatchRow:
    return HoursMatchRow(
        uploaded_name=name,
        uploaded_id=external_id,
        client="Acme Corp",
        hours=hours,
        month="",
        source_row=1,
    )


def _run(db, cycle, candidates, hours: float):
    year, month = (int(p) for p in cycle.incentive_month.split("-"))
    rows = [_hours_row(c.candidate_name, c.external_candidate_id, hours) for c in candidates]
    return run_cycle_calculation(db, cycle, rows, _window(year, month))


def _payable(lines, role: str, candidate_id=None):
    out = [line for line in lines if line.role == role and line.eligible and line.amount > 0]
    if candidate_id is not None:
        out = [line for line in out if line.candidate_id == candidate_id]
    return out


def _blocked(lines, role: str, candidate_id=None):
    out = [
        line
        for line in lines
        if line.role == role and not line.eligible and "duplicate" in (line.reason or "").lower()
    ]
    if candidate_id is not None:
        out = [line for line in out if line.candidate_id == candidate_id]
    return out


def _persist(db, cycle, lines, status=CycleStatus.APPROVED) -> None:
    rows = []
    for line in lines:
        rows.append(
            {
                "candidate_id": line.candidate_id,
                "candidate_name": line.candidate_name,
                "role": line.role,
                "person": line.person,
                "incentive_type": line.incentive_type,
                "rule_applied": line.rule_applied,
                "eligible": line.eligible,
                "base_incentive": line.base_incentive,
                "pro_rata_factor": line.pro_rata_factor,
                "amount": line.amount,
                "hours": line.hours,
                "reason": line.reason,
                "explanation_json": line.explanation_json(),
            }
        )
    incentive_repository.replace_cycle_lines(db, cycle.id, rows)
    cycle.status = status
    db.add(cycle)
    db.flush()


def test_first_run_creates_recruiter_and_team_lead():
    db = _session()
    cand = _seed_candidate(db, external_id="A-001", name="Person A")
    _seed_coordinators(db)
    cycle = _cycle(db, "2026-08")
    lines, _, _, _ = _run(db, cycle, [cand], 180)
    rec = _payable(lines, "Recruiter")
    tl = _payable(lines, "Team Lead")
    assert len(rec) == 1
    assert len(tl) == 1
    _, rec_amt = nashik_pro_rata(Decimal("2000"), Decimal("180"))
    _, tl_amt = nashik_pro_rata(TEAM_LEAD_BASE, Decimal("180"))
    assert rec[0].amount == rec_amt
    assert tl[0].amount == tl_amt
    assert rec[0].incentive_type == "RECURRING"
    assert tl[0].incentive_type == "RECURRING"


def test_second_same_month_cycle_skips_recruiter_and_team_lead():
    db = _session()
    cand = _seed_candidate(db, external_id="A-001", name="Person A")
    _seed_coordinators(db)
    first = _cycle(db, "2026-08")
    first_lines, _, _, _ = _run(db, first, [cand], 180)
    _persist(db, first, first_lines, CycleStatus.CALCULATED)

    second = _cycle(db, "2026-08")
    second_lines, stats, _, _ = _run(db, second, [cand], 180)
    assert _payable(second_lines, "Recruiter", cand.id) == []
    assert _payable(second_lines, "Team Lead", cand.id) == []
    assert _blocked(second_lines, "Recruiter", cand.id)
    assert _blocked(second_lines, "Team Lead", cand.id)
    assert stats["already_paid"] >= 2


def test_different_month_creates_recruiter_and_team_lead():
    db = _session()
    cand = _seed_candidate(db, external_id="A-001", name="Person A")
    _seed_coordinators(db)
    august = _cycle(db, "2026-08")
    august_lines, _, _, _ = _run(db, august, [cand], 180)
    _persist(db, august, august_lines)

    september = _cycle(db, "2026-09")
    sept_lines, _, _, _ = _run(db, september, [cand], 160)
    assert len(_payable(sept_lines, "Recruiter", cand.id)) == 1
    assert len(_payable(sept_lines, "Team Lead", cand.id)) == 1


def test_different_candidate_same_month_creates():
    db = _session()
    person_a = _seed_candidate(db, external_id="A-001", name="Person A")
    person_b = _seed_candidate(db, external_id="B-001", name="Person B")
    _seed_coordinators(db)
    first = _cycle(db, "2026-08")
    first_lines, _, _, _ = _run(db, first, [person_a], 180)
    _persist(db, first, first_lines)

    second = _cycle(db, "2026-08")
    second_lines, _, _, _ = _run(db, second, [person_a, person_b], 160)
    assert _payable(second_lines, "Recruiter", person_a.id) == []
    assert _payable(second_lines, "Team Lead", person_a.id) == []
    assert len(_payable(second_lines, "Recruiter", person_b.id)) == 1
    assert len(_payable(second_lines, "Team Lead", person_b.id)) == 1


def test_same_candidate_month_roles_are_independent():
    db = _session()
    cand = _seed_candidate(db, external_id="A-001", name="Person A")
    _seed_coordinators(db)
    first = _cycle(db, "2026-08")
    first_lines, _, _, _ = _run(db, first, [cand], 180)
    recruiter_only = [line for line in first_lines if line.role == "Recruiter"]
    _persist(db, first, recruiter_only)

    second = _cycle(db, "2026-08")
    second_lines, _, _, _ = _run(db, second, [cand], 180)
    assert _payable(second_lines, "Recruiter", cand.id) == []
    assert _blocked(second_lines, "Recruiter", cand.id)
    assert len(_payable(second_lines, "Team Lead", cand.id)) == 1


def test_one_time_leadership_duplicate_unchanged():
    db = _session()
    cand = _seed_candidate(db, external_id="A-001", name="Person A")
    _seed_coordinators(db)
    first = _cycle(db, "2026-08")
    first_lines, _, _, _ = _run(db, first, [cand], 180)
    assert len(_payable(first_lines, "Manager")) == 1
    assert len(_payable(first_lines, "CRM")) == 1
    _persist(db, first, first_lines)

    second = _cycle(db, "2026-08")
    second_lines, _, _, _ = _run(db, second, [cand], 180)
    for role in ("Manager", "CRM"):
        assert _payable(second_lines, role) == []
        assert _blocked(second_lines, role)
        assert "already paid" in (_blocked(second_lines, role)[0].reason or "").lower()

    september = _cycle(db, "2026-09")
    sept_lines, _, _, _ = _run(db, september, [cand], 160)
    assert _payable(sept_lines, "Manager") == []
    assert _payable(sept_lines, "CRM") == []


def test_same_cycle_recalculate_does_not_increase_records():
    db = _session()
    cand = _seed_candidate(db, external_id="A-001", name="Person A")
    _seed_coordinators(db)
    cycle = _cycle(db, "2026-08")
    first_lines, _, _, _ = _run(db, cycle, [cand], 180)
    _persist(db, cycle, first_lines, CycleStatus.CALCULATED)
    first_count = len(
        [
            line
            for line in first_lines
            if line.role in {"Recruiter", "Team Lead"} and line.eligible and line.amount > 0
        ]
    )
    rerun_lines, _, _, _ = _run(db, cycle, [cand], 180)
    _persist(db, cycle, rerun_lines, CycleStatus.CALCULATED)
    persisted = incentive_repository.list_lines(db, cycle.id)
    payable = [
        line
        for line in persisted
        if line.role in {"Recruiter", "Team Lead"} and line.eligible and Decimal(str(line.amount or 0)) > 0
    ]
    assert len(payable) == first_count == 2


def test_repository_keys_are_month_and_nashik_scoped():
    db = _session()
    cand = _seed_candidate(db, external_id="A-001", name="Person A")
    _seed_coordinators(db)
    august = _cycle(db, "2026-08")
    august_lines, _, _, _ = _run(db, august, [cand], 180)
    _persist(db, august, august_lines, CycleStatus.CALCULATED)

    august_keys = incentive_repository.paid_nashik_recurring_month_keys(db, -1, "2026-08")
    assert f"{cand.id}|RECURRING|Recruiter|2026-08" in august_keys
    assert f"{cand.id}|RECURRING|Team Lead|2026-08" in august_keys

    september_keys = incentive_repository.paid_nashik_recurring_month_keys(db, -1, "2026-09")
    assert september_keys == set()

    other = _cycle(db, "2026-08", division="sambhajiNagar")
    other_lines = [
        line
        for line in august_lines
        if line.role in {"Recruiter", "Team Lead"} and line.eligible
    ]
    _persist(db, other, other_lines, CycleStatus.CALCULATED)
    keys_excluding_nashik_cycle = incentive_repository.paid_nashik_recurring_month_keys(
        db, august.id, "2026-08"
    )
    assert keys_excluding_nashik_cycle == set()
