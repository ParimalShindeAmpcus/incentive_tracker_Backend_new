from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.entities.candidate import Candidate, CandidateDataVersion
from app.repositories.entities.cycle import CycleStatus, IncentiveCycle
from app.services.cycles.cycle_engine import run_cycle_calculation
from app.services.cycles.hours_name_matcher import HoursMatchRow
from app.services.incentives.nashik_calculator import CycleWindow


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _seed_candidate(db, **kwargs):
    version = CandidateDataVersion(version_label="v1", division="nashik")
    db.add(version)
    db.flush()
    data = dict(
        external_candidate_id="12345",
        start_id="12345",
        candidate_name="Aisha Mayes",
        normalized_name="aisha mayes",
        contract_type="C2C",
        margin=Decimal("12"),
        recruiter="Amit William Ohol",
        team_lead="Majid Khan",
        manager="Nitin Giri",
        crm="David",
        center_head="ABC",
        avp="DEF",
        organization="Ampcus Inc",
        candidate_source="Ampcus Inc",
        recruiter_location="Nashik",
        start_date=date(2026, 1, 1),
        division="nashik",
        source_version_id=version.id,
        last_touched_version_id=version.id,
        incentive_active=True,
        is_active=True,
    )
    data.update(kwargs)
    cand = Candidate(**data)
    db.add(cand)
    db.flush()
    return cand


def _cycle(db):
    cycle = IncentiveCycle(
        name="Nashik Aug",
        division="nashik",
        incentive_month="2026-08",
        cycle_start_date=date(2026, 8, 1),
        cycle_end_date=date(2026, 8, 31),
        status=CycleStatus.DRAFT,
    )
    db.add(cycle)
    db.flush()
    return cycle


WINDOW = CycleWindow(start=date(2026, 8, 1), end=date(2026, 8, 31))


def test_calculate_creates_lines_for_name_and_id_match():
    db = _session()
    _seed_candidate(db)
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Aisha Mayes", uploaded_id="12345", hours=160)]
    lines, stats, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    recruiter = next(line for line in lines if line.role == "Recruiter" and line.eligible)
    assert recruiter.amount == Decimal("3500")
    assert stats["matched_name_and_id"] == 1
    assert any(line.role == "Team Lead" and line.amount == Decimal("250") for line in lines)
    assert any(line.role == "Manager" and line.eligible for line in lines)


def test_name_id_mismatch_does_not_pay():
    db = _session()
    _seed_candidate(db)
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Aisha Mayes", uploaded_id="99999", hours=160)]
    lines, stats, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    assert stats["name_id_mismatch"] == 1
    assert all((not line.eligible) or line.amount == 0 for line in lines)


def test_eighty_hours_prorata():
    db = _session()
    _seed_candidate(db, margin=Decimal("8"))
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Aisha Mayes", uploaded_id="12345", hours=80)]
    lines, _, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    recruiter = next(line for line in lines if line.role == "Recruiter" and line.eligible)
    assert recruiter.amount == Decimal("1000")
    tl = next(line for line in lines if line.role == "Team Lead")
    assert tl.amount == Decimal("125")


def test_project_end_before_160():
    db = _session()
    _seed_candidate(db, end_date=date(2026, 8, 10), margin=Decimal("8"))
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Aisha Mayes", uploaded_id="12345", hours=80)]
    lines, _, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    recruiter = next(line for line in lines if line.role == "Recruiter")
    assert recruiter.amount == Decimal("2000")
    assert recruiter.incentive_type == "SPECIAL"
    assert all(line.role != "Team Lead" or line.amount == 0 for line in lines)


def test_missing_hierarchy_does_not_invent_roles():
    db = _session()
    _seed_candidate(db, team_lead=None, manager=None, crm=None, center_head=None, avp=None, margin=Decimal("8"))
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Aisha Mayes", uploaded_id="12345", hours=160)]
    lines, _, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    roles = {line.role for line in lines if line.eligible and line.amount > 0}
    assert roles == {"Recruiter"}


def test_id_fallback_still_calculates():
    db = _session()
    _seed_candidate(db)
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Aisha Mays", uploaded_id="12345", hours=160)]
    lines, stats, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    assert stats["matched_id_fallback"] == 1
    recruiter = next(line for line in lines if line.role == "Recruiter" and line.eligible)
    assert recruiter.amount == Decimal("3500")


def test_unmatched_does_not_pay():
    db = _session()
    _seed_candidate(db)
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Unknown Candidate", uploaded_id="UNKNOWN123", hours=160)]
    lines, stats, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    assert stats["unmatched"] == 1
    assert all((not line.eligible) or line.amount == 0 for line in lines)


def test_explanation_includes_master_start_contract_margin():
    db = _session()
    _seed_candidate(db)
    cycle = _cycle(db)
    rows = [HoursMatchRow(uploaded_name="Aisha Mayes", uploaded_id="12345", hours=160)]
    lines, _, _, _ = run_cycle_calculation(db, cycle, rows, WINDOW)
    recruiter = next(line for line in lines if line.role == "Recruiter" and line.eligible)
    import json

    payload = json.loads(recruiter.explanation[0])
    assert payload["start_date"] == "2026-01-01"
    assert payload["contract_type"] == "C2C"
    assert payload["margin_per_hour"] == 12.0
    assert payload["candidate_id"] == "12345"
