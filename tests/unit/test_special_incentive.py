"""Unit tests for Special Incentive (Recruiter of the Month)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.special_incentive import special_incentive_service as svc


def _cand(**kwargs):
    defaults = dict(
        id=1,
        external_candidate_id="EXT-1",
        start_id="CAND-1",
        activity_id=None,
        candidate_name="Candidate",
        organization="Ampcus Inc",
        recruiter="Rahul Sharma",
        client="Acme",
        start_date=date(2026, 9, 5),
        margin=Decimal("10"),
        contract_type="W2",
        is_active=True,
        incentive_active=True,
        division="nashik",
        candidate_source="Ampcus Inc",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_organization_matches_ampcus_not_tech():
    assert svc.organization_matches("Ampcus Inc", "Ampcus Inc")
    assert svc.organization_matches("ampcus", "Ampcus Inc")
    assert not svc.organization_matches("Ampcus Tech", "Ampcus Inc")
    assert not svc.organization_matches("Ampcus Tech Inhouse", "Ampcus Inc")


def test_organization_matches_bravens():
    assert svc.organization_matches("Bravens Inc", "Bravens Inc")
    assert not svc.organization_matches("BravensTech", "Bravens Inc")


def test_month_bounds_start_id_month():
    start, end = svc.month_bounds("2026-09")
    assert start == date(2026, 9, 1)
    assert end == date(2026, 10, 1)


def test_invalid_month_raises():
    with pytest.raises(HTTPException) as exc:
        svc.parse_month_key("2026/09")
    assert exc.value.status_code == 400


def test_highest_placements_and_margin_isolated(monkeypatch):
    rows = [
        _cand(id=1, recruiter="Rahul Sharma", organization="Ampcus Inc", margin=Decimal("12"), start_date=date(2026, 9, 2)),
        _cand(id=2, recruiter="Rahul Sharma", organization="Ampcus Inc", margin=Decimal("15"), start_date=date(2026, 9, 8), candidate_name="B"),
        _cand(id=3, recruiter="Amit Patil", organization="Ampcus Inc", margin=Decimal("42.5"), start_date=date(2026, 9, 10), candidate_name="John Smith"),
        _cand(id=4, recruiter="Priya Sharma", organization="Bravens Inc", margin=Decimal("20"), start_date=date(2026, 9, 3), candidate_name="P1"),
        _cand(id=5, recruiter="Priya Sharma", organization="Bravens Inc", margin=Decimal("22"), start_date=date(2026, 9, 4), candidate_name="P2"),
        _cand(id=6, recruiter="Neha Patel", organization="Bravens Inc", margin=Decimal("47.5"), start_date=date(2026, 9, 18), candidate_name="XYZ"),
        _cand(id=7, recruiter="Rahul Sharma", organization="Ampcus Inc", margin=Decimal("99"), start_date=date(2026, 8, 1), candidate_name="Old"),
        _cand(id=8, recruiter="Other", organization="Ampcus Tech", margin=Decimal("100"), start_date=date(2026, 9, 1), candidate_name="Tech"),
    ]

    monkeypatch.setattr(svc.candidate_repository, "list_all_candidates", lambda db: rows)
    monkeypatch.setattr(svc, "is_seed_candidate", lambda c: False)

    result = svc.get_special_incentive(SimpleNamespace(), "2026-09")
    assert result.month == "2026-09"
    assert result.source == "candidate_master"
    assert len(result.organizations) == 2

    ampcus = next(o for o in result.organizations if o.key == "ampcus_inc")
    bravens = next(o for o in result.organizations if o.key == "bravens_inc")

    assert ampcus.highest_placements.winners[0].recruiter == "Rahul Sharma"
    assert ampcus.highest_placements.winners[0].placement_count == 2
    assert ampcus.highest_placements.winners[0].incentive == 5000
    assert len(ampcus.highest_placements.winners[0].candidates) == 2

    assert ampcus.highest_margin.winners[0].recruiter == "Amit Patil"
    assert ampcus.highest_margin.winners[0].candidate_name == "John Smith"
    assert ampcus.highest_margin.winners[0].c3_margin == 42.5

    assert bravens.highest_placements.winners[0].recruiter == "Priya Sharma"
    assert bravens.highest_placements.winners[0].placement_count == 2
    assert bravens.highest_margin.winners[0].recruiter == "Neha Patel"
    assert bravens.highest_margin.winners[0].c3_margin == 47.5

    for c in ampcus.highest_placements.winners[0].candidates:
        assert c.organization and "Bravens" not in c.organization


def test_placement_tie_explicit(monkeypatch):
    rows = [
        _cand(id=1, recruiter="Rahul Sharma", organization="Ampcus Inc", start_date=date(2026, 9, 1)),
        _cand(id=2, recruiter="Amit Patil", organization="Ampcus Inc", start_date=date(2026, 9, 2), candidate_name="B"),
    ]
    monkeypatch.setattr(svc.candidate_repository, "list_all_candidates", lambda db: rows)
    monkeypatch.setattr(svc, "is_seed_candidate", lambda c: False)
    monkeypatch.setattr(
        svc,
        "get_settings",
        lambda: SimpleNamespace(special_incentive_tie_pay_all=True),
    )

    result = svc.get_special_incentive(SimpleNamespace(), "2026-09")
    ampcus = result.organizations[0]
    assert ampcus.highest_placements.is_tie is True
    assert len(ampcus.highest_placements.winners) == 2
    assert all(w.placement_count == 1 for w in ampcus.highest_placements.winners)
    assert all(w.incentive == 5000 for w in ampcus.highest_placements.winners)


def test_margin_tie_withhold_when_configured(monkeypatch):
    rows = [
        _cand(id=1, recruiter="A", organization="Ampcus Inc", margin=Decimal("50"), start_date=date(2026, 9, 1), candidate_name="X"),
        _cand(id=2, recruiter="B", organization="Ampcus Inc", margin=Decimal("50"), start_date=date(2026, 9, 2), candidate_name="Y"),
    ]
    monkeypatch.setattr(svc.candidate_repository, "list_all_candidates", lambda db: rows)
    monkeypatch.setattr(svc, "is_seed_candidate", lambda c: False)
    monkeypatch.setattr(
        svc,
        "get_settings",
        lambda: SimpleNamespace(special_incentive_tie_pay_all=False),
    )

    result = svc.get_special_incentive(SimpleNamespace(), "2026-09")
    award = result.organizations[0].highest_margin
    assert award.is_tie is True
    assert len(award.winners) == 2
    assert all(w.incentive == 0 for w in award.winners)


def test_margin_same_recruiter_multiple_candidates_shows_once(monkeypatch):
    """Rahul should appear once even if 3 of his candidates share the top C3 margin."""
    rows = [
        _cand(id=1, recruiter="Amit Verma", organization="Ampcus Inc", margin=Decimal("20"), start_date=date(2026, 9, 1), candidate_name="Ramesh Patwardhan"),
        _cand(id=2, recruiter="Rahul Sharma", organization="Ampcus Inc", margin=Decimal("20"), start_date=date(2026, 9, 2), candidate_name="Omkar Jagtap"),
        _cand(id=3, recruiter="Rahul Sharma", organization="Ampcus Inc", margin=Decimal("20"), start_date=date(2026, 9, 3), candidate_name="Snehal More"),
        _cand(id=4, recruiter="Rahul Sharma", organization="Ampcus Inc", margin=Decimal("20"), start_date=date(2026, 9, 4), candidate_name="Yash Deshpande"),
        _cand(id=5, recruiter="Other", organization="Ampcus Inc", margin=Decimal("10"), start_date=date(2026, 9, 5), candidate_name="Low"),
    ]
    monkeypatch.setattr(svc.candidate_repository, "list_all_candidates", lambda db: rows)
    monkeypatch.setattr(svc, "is_seed_candidate", lambda c: False)

    result = svc.get_special_incentive(SimpleNamespace(), "2026-09")
    award = result.organizations[0].highest_margin
    assert award.is_tie is True
    assert len(award.winners) == 2
    rahul = next(w for w in award.winners if w.recruiter == "Rahul Sharma")
    amit = next(w for w in award.winners if w.recruiter == "Amit Verma")
    assert rahul.candidate_count == 3
    assert len(rahul.candidates) == 3
    assert {c.candidate_name for c in rahul.candidates} == {"Omkar Jagtap", "Snehal More", "Yash Deshpande"}
    assert amit.candidate_count == 1

    details = svc.get_special_incentive_details(
        SimpleNamespace(),
        month="2026-09",
        organization_key="ampcus_inc",
        category="highest_margin",
        recruiter="Rahul Sharma",
    )
    assert len(details.candidates) == 3
    assert details.recruiter == "Rahul Sharma"


def test_details_placements(monkeypatch):
    rows = [
        _cand(id=1, recruiter="Rahul Sharma", organization="Ampcus Inc", start_date=date(2026, 9, 1), candidate_name="A"),
        _cand(id=2, recruiter="Rahul Sharma", organization="Ampcus Inc", start_date=date(2026, 9, 2), candidate_name="B"),
    ]
    monkeypatch.setattr(svc.candidate_repository, "list_all_candidates", lambda db: rows)
    monkeypatch.setattr(svc, "is_seed_candidate", lambda c: False)

    details = svc.get_special_incentive_details(
        SimpleNamespace(),
        month="2026-09",
        organization_key="ampcus_inc",
        category="highest_placements",
        recruiter="Rahul Sharma",
    )
    assert details.placement_count == 2
    assert len(details.candidates) == 2
    assert {c.candidate_name for c in details.candidates} == {"A", "B"}
