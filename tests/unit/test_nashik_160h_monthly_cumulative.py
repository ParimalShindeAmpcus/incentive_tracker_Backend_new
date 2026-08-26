"""
Nashik: Recruiter/Team Lead monthly pro-rata vs higher-hierarchy 160h cumulative.

Business rule (existing Nashik engine, not a parallel calculator):
  - Recruiter + Team Lead: each incentive month is evaluated on that month's hours
    and paid pro-rata for any hours below 160 (full amount at 160+). There is no
    separate monthly minimum.
  - Manager, CRM, Senior Manager, AVP, Director, Center Head: one-time only after
    the candidate's cumulative published hours reach 160. Never pro-rated, never duplicated.

Code path:
  Candidate Master → hours_rows (published) + cycle hours file
    → cycle_engine.run_cycle_calculation
    → nashik_calculator.calculate_nashik_placement
    → incentive_lines

Fixtures:
  tests/test_data/nashik_160h_candidate_master.csv
  tests/test_data/nashik_160h_coordinators.csv
  tests/test_data/nashik_160h_hours_{june,july,august}.csv
"""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.entities.candidate import Candidate, CandidateDataVersion
from app.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from app.repositories.entities.cycle import CycleStatus, IncentiveCycle
from app.repositories.hours import hours_repository
from app.repositories.incentives import incentive_repository
from app.services.cycles.cycle_engine import run_cycle_calculation
from app.services.cycles.hours_name_matcher import HoursMatchRow
from app.services.incentives.nashik_calculator import (
    CycleWindow,
    PlacementInput,
    calculate_nashik_placement,
)
from app.services.incentives.nashik_rules import (
    LEADERSHIP_ONE_TIME,
    TEAM_LEAD_BASE,
    nashik_pro_rata,
    normalize_person,
)

TEST_DATA = Path(__file__).resolve().parents[1] / "test_data"
CANDIDATE_ID = "NASHIK_TEST_160H_001"
CANDIDATE_NAME = "Nashik Incentive Test Candidate"
HIGHER_ROLES = (
    "Manager",
    "CRM",
    "Senior Manager",
    "AVP",
    "Director",
    "Center Head",
)
HIERARCHY = {
    "Recruiter": "TEST_RECRUITER_001",
    "Team Lead": "TEST_TL_001",
    "Manager": "TEST_MANAGER_001",
    "CRM": "TEST_CRM_001",
    "Senior Manager": "TEST_SM_001",
    "AVP": "TEST_AVP_001",
    "Director": "TEST_DIRECTOR_001",
    "Center Head": "TEST_CENTERHEAD_001",
}


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _window(year: int, month: int) -> CycleWindow:
    import calendar

    last = calendar.monthrange(year, month)[1]
    return CycleWindow(start=date(year, month, 1), end=date(year, month, last))


def _seed_candidate(db) -> Candidate:
    version = CandidateDataVersion(version_label="nashik-160h", division="nashik")
    db.add(version)
    db.flush()
    cand = Candidate(
        external_candidate_id=CANDIDATE_ID,
        start_id=CANDIDATE_ID,
        candidate_name=CANDIDATE_NAME,
        normalized_name=CANDIDATE_NAME.lower(),
        contract_type="C2C",
        margin=Decimal("8"),
        recruiter=HIERARCHY["Recruiter"],
        team_lead=HIERARCHY["Team Lead"],
        manager=HIERARCHY["Manager"],
        crm=HIERARCHY["CRM"],
        senior_manager=HIERARCHY["Senior Manager"],
        avp=HIERARCHY["AVP"],
        director=HIERARCHY["Director"],
        center_head=HIERARCHY["Center Head"],
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


def _publish_hours(db, cand: Candidate, month_key: str, hours: Decimal, label: str) -> None:
    version = hours_repository.create_version(
        db,
        version_label=label,
        division="nashik",
        source_filename=f"nashik_160h_hours_{month_key}.csv",
    )
    hours_repository.create_rows(
        db,
        version,
        [
            {
                "candidate_id": cand.id,
                "hours_worked": hours,
                "month_key": month_key,
                "client": "Acme Corp",
                "raw_candidate_name": cand.candidate_name,
                "match_method": "NAME_AND_ID",
                "match_confidence": "HIGH",
                "source_row": 1,
            }
        ],
    )


def _cycle(db, month_key: str) -> IncentiveCycle:
    year, month = (int(p) for p in month_key.split("-"))
    window = _window(year, month)
    cycle = IncentiveCycle(
        name=f"Nashik {month_key}",
        division="nashik",
        incentive_month=month_key,
        cycle_start_date=window.start,
        cycle_end_date=window.end,
        status=CycleStatus.DRAFT,
    )
    db.add(cycle)
    db.flush()
    return cycle


def _hours_row(hours: float) -> HoursMatchRow:
    return HoursMatchRow(
        uploaded_name=CANDIDATE_NAME,
        uploaded_id=CANDIDATE_ID,
        client="Acme Corp",
        hours=hours,
        month="",
        source_row=1,
    )


def _run(db, cycle, hours: float):
    year, month = (int(p) for p in cycle.incentive_month.split("-"))
    return run_cycle_calculation(db, cycle, [_hours_row(hours)], _window(year, month))


def _payable(lines, role: str):
    return [
        line
        for line in lines
        if line.role == role and line.eligible and line.amount > 0
    ]


def _amount(lines, role: str) -> Decimal:
    return sum((line.amount for line in _payable(lines, role)), Decimal("0"))


def _cumulative_from(lines) -> Optional[Decimal]:
    for line in lines:
        if not line.explanation:
            continue
        try:
            payload = json.loads(line.explanation[0])
        except (TypeError, json.JSONDecodeError, IndexError):
            continue
        if isinstance(payload, dict) and "cumulative_hours" in payload:
            return Decimal(str(payload["cumulative_hours"]))
    return None


def _seed_engine() -> tuple:
    db = _session()
    cand = _seed_candidate(db)
    _seed_coordinators(db)
    return db, cand


def _persist_payable_one_time(db, cycle, lines) -> None:
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
    cycle.status = CycleStatus.APPROVED
    db.add(cycle)
    db.flush()


def _assert_no_higher(lines, month_label: str) -> None:
    for role in HIGHER_ROLES:
        paid = _payable(lines, role)
        assert paid == [], f"{month_label}: {role} should have no incentive, got {paid}"


def _assert_monthly_recruiter_tl(lines, month_hours: Decimal, month_label: str) -> None:
    rec = _payable(lines, "Recruiter")
    tl = _payable(lines, "Team Lead")
    assert len(rec) == 1, f"{month_label}: Recruiter expected 1 payable line, got {len(rec)}"
    assert len(tl) == 1, f"{month_label}: Team Lead expected 1 payable line, got {len(tl)}"
    _, rec_amt = nashik_pro_rata(Decimal("2000"), month_hours)
    _, tl_amt = nashik_pro_rata(TEAM_LEAD_BASE, month_hours)
    assert rec[0].amount == rec_amt
    assert tl[0].amount == tl_amt
    assert rec[0].incentive_type == "RECURRING"
    assert tl[0].incentive_type == "RECURRING"


def test_fixture_files_exist_and_match_stable_id():
    candidate_rows = list(csv.DictReader((TEST_DATA / "nashik_160h_candidate_master.csv").open(encoding="utf-8")))
    coords = list(csv.DictReader((TEST_DATA / "nashik_160h_coordinators.csv").open(encoding="utf-8")))
    june = list(csv.DictReader((TEST_DATA / "nashik_160h_hours_june.csv").open(encoding="utf-8")))
    july = list(csv.DictReader((TEST_DATA / "nashik_160h_hours_july.csv").open(encoding="utf-8")))
    august = list(csv.DictReader((TEST_DATA / "nashik_160h_hours_august.csv").open(encoding="utf-8")))
    assert candidate_rows[0]["external_candidate_id"] == CANDIDATE_ID
    assert candidate_rows[0]["start_id"] == CANDIDATE_ID
    assert {row["Coordinator Name"] for row in coords} == set(HIERARCHY.values())
    assert june[0]["Hours Worked"] == "50" and june[0]["Candidate Start ID"] == CANDIDATE_ID
    assert july[0]["Hours Worked"] == "60" and july[0]["Candidate Start ID"] == CANDIDATE_ID
    assert august[0]["Hours Worked"] == "50" and august[0]["Candidate Start ID"] == CANDIDATE_ID


def test_june_july_august_monthly_vs_cumulative_and_no_duplicate():
    db = _session()
    cand = _seed_candidate(db)
    _seed_coordinators(db)
    recruiter_count = 0
    team_lead_count = 0

    _publish_hours(db, cand, "2026-06", Decimal("50"), "june")
    june_cycle = _cycle(db, "2026-06")
    june_lines, _, _, _ = _run(db, june_cycle, 50)
    _assert_monthly_recruiter_tl(june_lines, Decimal("50"), "June")
    _assert_no_higher(june_lines, "June")
    assert _cumulative_from(june_lines) == Decimal("50")
    recruiter_count += len(_payable(june_lines, "Recruiter"))
    team_lead_count += len(_payable(june_lines, "Team Lead"))
    assert cand.incentive_active is True
    assert cand.external_candidate_id == CANDIDATE_ID

    _publish_hours(db, cand, "2026-07", Decimal("60"), "july")
    july_cycle = _cycle(db, "2026-07")
    july_lines, _, _, _ = _run(db, july_cycle, 60)
    _assert_monthly_recruiter_tl(july_lines, Decimal("60"), "July")
    _assert_no_higher(july_lines, "July")
    assert _cumulative_from(july_lines) == Decimal("110")
    recruiter_count += len(_payable(july_lines, "Recruiter"))
    team_lead_count += len(_payable(july_lines, "Team Lead"))
    assert cand.external_candidate_id == CANDIDATE_ID

    _publish_hours(db, cand, "2026-08", Decimal("50"), "august")
    august_cycle = _cycle(db, "2026-08")
    august_lines, _, _, _ = _run(db, august_cycle, 50)
    _assert_monthly_recruiter_tl(august_lines, Decimal("50"), "August")
    assert _cumulative_from(august_lines) == Decimal("160")
    recruiter_count += len(_payable(august_lines, "Recruiter"))
    team_lead_count += len(_payable(august_lines, "Team Lead"))

    for role in HIGHER_ROLES:
        paid = _payable(august_lines, role)
        assert len(paid) == 1, f"August: {role} expected 1 incentive, got {len(paid)}"
        assert paid[0].incentive_type == "ONE_TIME"
        assert paid[0].amount == LEADERSHIP_ONE_TIME[role]
        assert paid[0].person == HIERARCHY[role]

    assert recruiter_count == 3
    assert team_lead_count == 3

    rerun_lines, _, _, _ = _run(db, august_cycle, 50)
    for role in HIGHER_ROLES:
        assert len(_payable(rerun_lines, role)) == 1, f"Re-run August must not duplicate {role}"
    assert len(_payable(rerun_lines, "Recruiter")) == 1
    assert len(_payable(rerun_lines, "Team Lead")) == 1

    _persist_payable_one_time(db, august_cycle, august_lines)
    second_august = _cycle(db, "2026-08")
    dup_lines, stats, _, _ = _run(db, second_august, 50)
    assert stats["already_paid"] >= len(HIGHER_ROLES)
    for role in HIGHER_ROLES:
        assert _payable(dup_lines, role) == [], f"Approved August must block a second {role} incentive"
        blocked = [line for line in dup_lines if line.role == role]
        assert blocked, f"{role} line should still be emitted as ineligible duplicate"
        assert "duplicate" in (blocked[0].reason or "").lower()
    assert len(_payable(dup_lines, "Recruiter")) == 1
    assert len(_payable(dup_lines, "Team Lead")) == 1


def test_edge_49_hours_still_pays_recruiter_tl_prorata():
    lines = calculate_nashik_placement(
        _placement(hours=Decimal("49"), cumulative_hours=Decimal("49")),
        _window(2026, 6),
    )
    _assert_monthly_recruiter_tl(lines, Decimal("49"), "49h")
    _assert_no_higher(lines, "49h")


def test_edge_50_hours_qualifies_recruiter_and_tl_not_higher():
    lines = calculate_nashik_placement(
        _placement(hours=Decimal("50"), cumulative_hours=Decimal("50")),
        _window(2026, 6),
    )
    _assert_monthly_recruiter_tl(lines, Decimal("50"), "50h")
    _assert_no_higher(lines, "50h")


def test_edge_59_then_50_cumulative_109_no_higher():
    first = calculate_nashik_placement(
        _placement(hours=Decimal("59"), cumulative_hours=Decimal("59")),
        _window(2026, 6),
    )
    _assert_monthly_recruiter_tl(first, Decimal("59"), "59h")
    _assert_no_higher(first, "59h")
    second = calculate_nashik_placement(
        _placement(hours=Decimal("50"), cumulative_hours=Decimal("109")),
        _window(2026, 7),
    )
    _assert_monthly_recruiter_tl(second, Decimal("50"), "59+50")
    _assert_no_higher(second, "cumulative 109")


def test_edge_50_60_49_cumulative_159_no_higher():
    lines = calculate_nashik_placement(
        _placement(hours=Decimal("49"), cumulative_hours=Decimal("159")),
        _window(2026, 8),
    )
    _assert_monthly_recruiter_tl(lines, Decimal("49"), "cumulative 159")
    _assert_no_higher(lines, "cumulative 159")


def test_edge_50_60_50_cumulative_160_higher_once():
    lines = calculate_nashik_placement(
        _placement(hours=Decimal("50"), cumulative_hours=Decimal("160")),
        _window(2026, 8),
    )
    _assert_monthly_recruiter_tl(lines, Decimal("50"), "cumulative 160")
    for role in HIGHER_ROLES:
        paid = _payable(lines, role)
        assert len(paid) == 1
        assert paid[0].amount == LEADERSHIP_ONE_TIME[role]


def test_engine_49_hours_still_pays_recruiter_tl_prorata():
    db, cand = _seed_engine()
    _publish_hours(db, cand, "2026-06", Decimal("49"), "june-49")
    cycle = _cycle(db, "2026-06")
    lines, _, _, _ = _run(db, cycle, 49)
    _assert_monthly_recruiter_tl(lines, Decimal("49"), "engine 49h")
    _assert_no_higher(lines, "engine 49h")
    assert _cumulative_from(lines) == Decimal("49")
    assert cand.incentive_active is True
    assert cand.external_candidate_id == CANDIDATE_ID


def test_engine_59_then_50_cumulative_109_no_higher():
    db, cand = _seed_engine()
    _publish_hours(db, cand, "2026-06", Decimal("59"), "june-59")
    june = _cycle(db, "2026-06")
    june_lines, _, _, _ = _run(db, june, 59)
    _assert_monthly_recruiter_tl(june_lines, Decimal("59"), "engine 59h")
    _assert_no_higher(june_lines, "engine 59h")

    _publish_hours(db, cand, "2026-07", Decimal("50"), "july-50")
    july = _cycle(db, "2026-07")
    july_lines, _, _, _ = _run(db, july, 50)
    _assert_monthly_recruiter_tl(july_lines, Decimal("50"), "engine 59+50")
    _assert_no_higher(july_lines, "engine cumulative 109")
    assert _cumulative_from(july_lines) == Decimal("109")
    assert cand.external_candidate_id == CANDIDATE_ID


def test_engine_50_60_49_cumulative_159_no_higher():
    db, cand = _seed_engine()
    _publish_hours(db, cand, "2026-06", Decimal("50"), "june")
    _publish_hours(db, cand, "2026-07", Decimal("60"), "july")
    _publish_hours(db, cand, "2026-08", Decimal("49"), "august-49")
    cycle = _cycle(db, "2026-08")
    lines, _, _, _ = _run(db, cycle, 49)
    assert hours_repository.sum_published_hours_before_month(db, cand.id, "2026-08") == Decimal("110")
    assert _cumulative_from(lines) == Decimal("159")
    _assert_monthly_recruiter_tl(lines, Decimal("49"), "engine cumulative 159")
    _assert_no_higher(lines, "engine cumulative 159")
    assert cand.external_candidate_id == CANDIDATE_ID


def test_published_hours_do_not_reset_across_months():
    db, cand = _seed_engine()
    _publish_hours(db, cand, "2026-06", Decimal("50"), "june")
    _publish_hours(db, cand, "2026-07", Decimal("60"), "july")
    _publish_hours(db, cand, "2026-08", Decimal("50"), "august")
    assert hours_repository.sum_published_hours_before_month(db, cand.id, "2026-06") == Decimal("0")
    assert hours_repository.sum_published_hours_before_month(db, cand.id, "2026-07") == Decimal("50")
    assert hours_repository.sum_published_hours_before_month(db, cand.id, "2026-08") == Decimal("110")
    assert hours_repository.sum_published_hours_before_month(db, cand.id, "2026-09") == Decimal("160")


def test_edge_160_cumulative_still_pays_monthly_recruiter_tl():
    lines = calculate_nashik_placement(
        _placement(hours=Decimal("50"), cumulative_hours=Decimal("210")),
        _window(2026, 9),
    )
    _assert_monthly_recruiter_tl(lines, Decimal("50"), "after 160")
    paid_keys = {line.paid_key() for line in lines if line.incentive_type == "ONE_TIME" and line.eligible}
    rerun = calculate_nashik_placement(
        _placement(hours=Decimal("50"), cumulative_hours=Decimal("210")),
        _window(2026, 9),
        paid_keys,
    )
    _assert_monthly_recruiter_tl(rerun, Decimal("50"), "after 160 rerun")
    _assert_no_higher(rerun, "after 160 rerun")


def _placement(**kwargs) -> PlacementInput:
    data = dict(
        candidate_pk=1,
        external_id=CANDIDATE_ID,
        name=CANDIDATE_NAME,
        contract_type="C2C",
        candidate_source="Ampcus Inc",
        organization="Ampcus Inc",
        recruiter_location="Nashik",
        start_date=date(2026, 1, 1),
        end_date=None,
        margin=Decimal("8"),
        hours=Decimal("50"),
        recruiter=HIERARCHY["Recruiter"],
        team_lead=HIERARCHY["Team Lead"],
        crm=HIERARCHY["CRM"],
        manager=HIERARCHY["Manager"],
        senior_manager=HIERARCHY["Senior Manager"],
        associate_director=None,
        center_head=HIERARCHY["Center Head"],
        avp=HIERARCHY["AVP"],
        director=HIERARCHY["Director"],
        incentive_active=True,
        project_ended=False,
    )
    data.update(kwargs)
    return PlacementInput(**data)
