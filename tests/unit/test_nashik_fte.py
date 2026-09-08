"""Unit tests for Nashik Division FTE incentive rules."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.cycles.engines.nashik_fte import (
    calculate_nashik_fte_placement,
    finder_fee_above_from_master,
    ninety_day_eligible_date,
)


def _cand(**kwargs):
    base = dict(
        id=101,
        candidate_name="FTE Candidate",
        contract_type="FULLTIME",
        start_date=date(2026, 1, 1),
        recruiter="Alice Recruiter",
        team_lead="Bob TL",
        manager="Carol Mgr",
        crm="Dan CRM",
        associate_director="Eve AD",
        center_head="Frank CH",
        candidate_source="Bravens",
        organization="Bravens",
        recruiter_location="Nashik",
        finder_fees="BELOW_500",
        margin=None,
        activity_id="ACT-1",
        start_id="ST-1",
        external_candidate_id="EXT-1",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _coord(name: str):
    return SimpleNamespace(
        name=name,
        employment_status=SimpleNamespace(value="ACTIVE"),
    )


def test_ninety_day_eligible_date():
    assert ninety_day_eligible_date(date(2026, 1, 1)) == date(2026, 4, 1)


def test_finder_fee_above_from_master():
    assert finder_fee_above_from_master(_cand(finder_fees="ABOVE_500")) is True
    assert finder_fee_above_from_master(_cand(finder_fees="BELOW_500")) is False
    assert finder_fee_above_from_master(_cand(finder_fees="NONE")) is False


def test_not_eligible_before_90_days():
    coordinators = {
        "alice recruiter": _coord("Alice Recruiter"),
        "bob tl": _coord("Bob TL"),
    }
    lines = calculate_nashik_fte_placement(
        _cand(start_date=date(2026, 1, 1)),
        payment_status="RECEIVED",
        coordinators=coordinators,
        cycle_end=date(2026, 2, 15),
        placement_count_this_month=1,
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.eligible is False
    assert recruiter.reason == "FTE_90_DAY_NOT_MET"
    assert recruiter.amount == Decimal("0")


def test_payment_received_pays_one_time_after_90_days():
    coordinators = {
        "alice recruiter": _coord("Alice Recruiter"),
        "bob tl": _coord("Bob TL"),
        "carol mgr": _coord("Carol Mgr"),
        "dan crm": _coord("Dan CRM"),
        "eve ad": _coord("Eve AD"),
        "frank ch": _coord("Frank CH"),
    }
    lines = calculate_nashik_fte_placement(
        _cand(finder_fees="BELOW_500"),
        payment_status="RECEIVED",
        coordinators=coordinators,
        cycle_end=date(2026, 4, 1),
        placement_count_this_month=1,
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.eligible is True
    assert recruiter.amount == Decimal("15000.00")
    assert "ONE_TIME_AFTER_90_DAYS" in (recruiter.explanation[0] or "")

    tl = next(l for l in lines if l.role == "Team Lead")
    assert tl.eligible is True
    assert tl.amount == Decimal("1000.00")
    assert tl.incentive_type == "ONE_TIME"


def test_payment_not_received_uses_installments():
    coordinators = {"alice recruiter": _coord("Alice Recruiter")}
    lines = calculate_nashik_fte_placement(
        _cand(finder_fees="BELOW_500", team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
        payment_status="PENDING",
        coordinators=coordinators,
        cycle_end=date(2026, 4, 1),
        placement_count_this_month=1,
        prior_recruiter_paid_amount=Decimal("0"),
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.eligible is True
    assert recruiter.amount == Decimal("5000.00")
    assert "INSTALLMENT_1/3" in (recruiter.explanation[0] or "")


def test_installment_2_after_prior_paid():
    coordinators = {"alice recruiter": _coord("Alice Recruiter")}
    lines = calculate_nashik_fte_placement(
        _cand(finder_fees="BELOW_500", team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
        payment_status="PENDING",
        coordinators=coordinators,
        cycle_end=date(2026, 5, 1),
        placement_count_this_month=1,
        prior_recruiter_paid_amount=Decimal("5000"),
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.amount == Decimal("5000.00")
    assert "INSTALLMENT_2/3" in (recruiter.explanation[0] or "")


def test_above_4500_two_placements_slab():
    coordinators = {"alice recruiter": _coord("Alice Recruiter")}
    lines = calculate_nashik_fte_placement(
        _cand(finder_fees="ABOVE_500", team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
        payment_status="RECEIVED",
        coordinators=coordinators,
        cycle_end=date(2026, 4, 1),
        placement_count_this_month=2,
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.amount == Decimal("25000.00")


def test_finder_fee_none_blocked():
    coordinators = {"alice recruiter": _coord("Alice Recruiter")}
    lines = calculate_nashik_fte_placement(
        _cand(finder_fees="NONE"),
        payment_status="RECEIVED",
        coordinators=coordinators,
        cycle_end=date(2026, 4, 1),
        placement_count_this_month=1,
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.eligible is False
    assert recruiter.reason == "FINDER_FEE_NOT_SET"
