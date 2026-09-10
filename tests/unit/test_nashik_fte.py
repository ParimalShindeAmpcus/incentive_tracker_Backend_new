"""Unit tests for Nashik Division FTE incentive rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.cycles.engines.nashik_fte import (
    build_nashik_fte_slab_counts,
    calculate_nashik_fte_placement,
    finder_fee_above_from_master,
    nashik_fte_placement_count_for_candidate,
    ninety_day_eligible_date,
    placement_month_from_start,
)
from app.services.cycles.engines.sambhaji_nagar import fte_recruiter_amount


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


def _recruiter_amount_for(candidate, placement_count: int) -> Decimal:
    lines = calculate_nashik_fte_placement(
        candidate,
        payment_status="RECEIVED",
        coordinators={"alice recruiter": _coord("Alice Recruiter")},
        cycle_end=date(2026, 7, 31),  # cycle run later than January placement
        placement_count_this_month=placement_count,
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    return recruiter.amount


def test_ninety_day_eligible_date():
    assert ninety_day_eligible_date(date(2026, 1, 1)) == date(2026, 4, 1)


def test_finder_fee_above_from_master():
    assert finder_fee_above_from_master(_cand(finder_fees="ABOVE_500")) is True
    assert finder_fee_above_from_master(_cand(finder_fees="BELOW_500")) is False
    assert finder_fee_above_from_master(_cand(finder_fees="NONE")) is False


def test_placement_month_from_start_ignores_cycle_month():
    assert placement_month_from_start(date(2026, 1, 15), fallback_month="2026-07") == "2026-01"
    assert placement_month_from_start(None, fallback_month="2026-07") == "2026-07"


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
        _cand(
            finder_fees="BELOW_500",
            team_lead=None,
            manager=None,
            crm=None,
            associate_director=None,
            center_head=None,
        ),
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
        _cand(
            finder_fees="BELOW_500",
            team_lead=None,
            manager=None,
            crm=None,
            associate_director=None,
            center_head=None,
        ),
        payment_status="PENDING",
        coordinators=coordinators,
        cycle_end=date(2026, 5, 1),
        placement_count_this_month=1,
        prior_recruiter_paid_amount=Decimal("5000"),
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.amount == Decimal("5000.00")
    assert "INSTALLMENT_2/3" in (recruiter.explanation[0] or "")


def test_already_paid_blocks_duplicate_recruiter_payout():
    coordinators = {"alice recruiter": _coord("Alice Recruiter")}
    lines = calculate_nashik_fte_placement(
        _cand(
            finder_fees="BELOW_500",
            team_lead=None,
            manager=None,
            crm=None,
            associate_director=None,
            center_head=None,
        ),
        payment_status="RECEIVED",
        coordinators=coordinators,
        cycle_end=date(2026, 7, 31),
        placement_count_this_month=1,
        prior_recruiter_paid_amount=Decimal("15000"),
    )
    recruiter = next(l for l in lines if l.role == "Recruiter")
    assert recruiter.eligible is False
    assert recruiter.reason == "ALREADY_PAID"
    assert recruiter.amount == Decimal("0")


def test_above_4500_two_placements_slab():
    coordinators = {"alice recruiter": _coord("Alice Recruiter")}
    lines = calculate_nashik_fte_placement(
        _cand(
            finder_fees="ABOVE_500",
            team_lead=None,
            manager=None,
            crm=None,
            associate_director=None,
            center_head=None,
        ),
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


# ── Mandatory fee-category slab cases ─────────────────────────────────────────

def test_slab_1_below_4500():
    assert _recruiter_amount_for(_cand(finder_fees="BELOW_500"), 1) == Decimal("15000.00")
    assert fte_recruiter_amount(False, 1) == 15000


def test_slab_1_above_4500():
    assert _recruiter_amount_for(_cand(finder_fees="ABOVE_500"), 1) == Decimal("20000.00")
    assert fte_recruiter_amount(True, 1) == 20000


def test_slab_2_below_4500():
    assert _recruiter_amount_for(_cand(finder_fees="BELOW_500"), 2) == Decimal("18000.00")
    assert fte_recruiter_amount(False, 2) == 18000


def test_slab_2_above_4500():
    assert _recruiter_amount_for(_cand(finder_fees="ABOVE_500"), 2) == Decimal("25000.00")
    assert fte_recruiter_amount(True, 2) == 25000


def test_slab_3_below_4500():
    assert _recruiter_amount_for(_cand(finder_fees="BELOW_500"), 3) == Decimal("20000.00")
    assert fte_recruiter_amount(False, 3) == 20000


def test_slab_3_above_4500():
    assert _recruiter_amount_for(_cand(finder_fees="ABOVE_500"), 3) == Decimal("30000.00")
    assert fte_recruiter_amount(True, 3) == 30000


def test_mixed_2_below_1_above_independent_counts():
    """2 below + 1 above → ₹18k + ₹18k + ₹20k (not a combined count of 3)."""
    candidates = [
        _cand(id=1, candidate_name="A", finder_fees="BELOW_500", start_date=date(2026, 1, 5)),
        _cand(id=2, candidate_name="B", finder_fees="BELOW_500", start_date=date(2026, 1, 10)),
        _cand(id=3, candidate_name="C", finder_fees="ABOVE_500", start_date=date(2026, 1, 20)),
    ]
    counts = build_nashik_fte_slab_counts(candidates)
    assert nashik_fte_placement_count_for_candidate(candidates[0], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[1], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[2], counts) == 1

    assert _recruiter_amount_for(candidates[0], 2) == Decimal("18000.00")
    assert _recruiter_amount_for(candidates[1], 2) == Decimal("18000.00")
    assert _recruiter_amount_for(candidates[2], 1) == Decimal("20000.00")
    total = Decimal("18000.00") + Decimal("18000.00") + Decimal("20000.00")
    assert total == Decimal("56000.00")


def test_mixed_1_below_2_above_independent_counts():
    """1 below + 2 above → ₹15k + ₹25k + ₹25k."""
    candidates = [
        _cand(id=1, candidate_name="A", finder_fees="BELOW_500", start_date=date(2026, 1, 5)),
        _cand(id=2, candidate_name="B", finder_fees="ABOVE_500", start_date=date(2026, 1, 10)),
        _cand(id=3, candidate_name="C", finder_fees="ABOVE_500", start_date=date(2026, 1, 20)),
    ]
    counts = build_nashik_fte_slab_counts(candidates)
    assert nashik_fte_placement_count_for_candidate(candidates[0], counts) == 1
    assert nashik_fte_placement_count_for_candidate(candidates[1], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[2], counts) == 2

    amounts = [
        _recruiter_amount_for(candidates[0], 1),
        _recruiter_amount_for(candidates[1], 2),
        _recruiter_amount_for(candidates[2], 2),
    ]
    assert amounts == [Decimal("15000.00"), Decimal("25000.00"), Decimal("25000.00")]
    assert sum(amounts) == Decimal("65000.00")


def test_mixed_3_below_2_above_end_to_end_amounts():
    """3 below + 2 above must pay 20k×3 + 25k×2 — never 30k on the above pair."""
    candidates = [
        _cand(id=1, finder_fees="BELOW_500", start_date=date(2026, 1, 1), team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
        _cand(id=2, finder_fees="BELOW_500", start_date=date(2026, 1, 2), team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
        _cand(id=3, finder_fees="BELOW_500", start_date=date(2026, 1, 3), team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
        _cand(id=4, finder_fees="ABOVE_500", start_date=date(2026, 1, 4), team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
        _cand(id=5, finder_fees="ABOVE_500", start_date=date(2026, 1, 5), team_lead=None, manager=None, crm=None, associate_director=None, center_head=None),
    ]
    counts = build_nashik_fte_slab_counts(candidates)
    amounts = []
    for c in candidates:
        n = nashik_fte_placement_count_for_candidate(c, counts)
        amounts.append(_recruiter_amount_for(c, n))
    assert amounts == [
        Decimal("20000.00"),
        Decimal("20000.00"),
        Decimal("20000.00"),
        Decimal("25000.00"),
        Decimal("25000.00"),
    ]
    assert sum(amounts) == Decimal("110000.00")
    assert Decimal("30000.00") not in amounts


def test_different_recruiters_do_not_share_counts():
    candidates = [
        _cand(id=1, recruiter="Alice Recruiter", finder_fees="BELOW_500", start_date=date(2026, 1, 1)),
        _cand(id=2, recruiter="Alice Recruiter", finder_fees="BELOW_500", start_date=date(2026, 1, 2)),
        _cand(id=3, recruiter="Other Recruiter", finder_fees="BELOW_500", start_date=date(2026, 1, 3)),
    ]
    counts = build_nashik_fte_slab_counts(candidates)
    assert nashik_fte_placement_count_for_candidate(candidates[0], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[1], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[2], counts) == 1


def test_different_placement_months_do_not_share_counts():
    candidates = [
        _cand(id=1, finder_fees="ABOVE_500", start_date=date(2026, 1, 10)),
        _cand(id=2, finder_fees="ABOVE_500", start_date=date(2026, 1, 20)),
        _cand(id=3, finder_fees="ABOVE_500", start_date=date(2026, 2, 5)),
    ]
    counts = build_nashik_fte_slab_counts(candidates)
    assert nashik_fte_placement_count_for_candidate(candidates[0], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[1], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[2], counts) == 1


def test_cycle_run_in_july_still_groups_by_january_placement_month():
    """Cycle executed in July must still use January start dates for slab grouping."""
    candidates = [
        _cand(id=1, finder_fees="BELOW_500", start_date=date(2026, 1, 5)),
        _cand(id=2, finder_fees="ABOVE_500", start_date=date(2026, 1, 12)),
        _cand(id=3, finder_fees="ABOVE_500", start_date=date(2026, 1, 18)),
    ]
    # fallback_month simulates cycle incentive_month = July — must not override start month
    counts = build_nashik_fte_slab_counts(candidates, fallback_month="2026-07")
    assert all(placement_month_from_start(c.start_date) == "2026-01" for c in candidates)
    assert nashik_fte_placement_count_for_candidate(candidates[0], counts, fallback_month="2026-07") == 1
    assert nashik_fte_placement_count_for_candidate(candidates[1], counts, fallback_month="2026-07") == 2
    assert nashik_fte_placement_count_for_candidate(candidates[2], counts, fallback_month="2026-07") == 2

    # Amounts still use January-derived category counts even when cycle_end is July
    assert _recruiter_amount_for(candidates[0], 1) == Decimal("15000.00")
    assert _recruiter_amount_for(candidates[1], 2) == Decimal("25000.00")
    assert _recruiter_amount_for(candidates[2], 2) == Decimal("25000.00")


def test_unset_finder_fee_excluded_from_slab_counts():
    candidates = [
        _cand(id=1, finder_fees="BELOW_500", start_date=date(2026, 1, 1)),
        _cand(id=2, finder_fees="NONE", start_date=date(2026, 1, 2)),
        _cand(id=3, finder_fees="BELOW_500", start_date=date(2026, 1, 3)),
    ]
    counts = build_nashik_fte_slab_counts(candidates)
    assert nashik_fte_placement_count_for_candidate(candidates[0], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[2], counts) == 2


def test_inactive_candidate_excluded_from_slab_counts():
    """Inactive Candidate Master rows must not inflate above/below 4500 counts."""
    candidates = [
        _cand(id=1, finder_fees="BELOW_500", start_date=date(2026, 1, 1)),
        _cand(
            id=2,
            finder_fees="BELOW_500",
            start_date=date(2026, 1, 2),
            incentive_active=False,
            status="Inactive (Excluded)",
        ),
        _cand(id=3, finder_fees="BELOW_500", start_date=date(2026, 1, 3)),
        _cand(
            id=4,
            finder_fees="ABOVE_500",
            start_date=date(2026, 1, 4),
            incentive_active=False,
        ),
        _cand(id=5, finder_fees="ABOVE_500", start_date=date(2026, 1, 5)),
    ]
    counts = build_nashik_fte_slab_counts(candidates)
    # Only active BELOW placements (id 1 and 3) count → 2
    assert nashik_fte_placement_count_for_candidate(candidates[0], counts) == 2
    assert nashik_fte_placement_count_for_candidate(candidates[2], counts) == 2
    # Only active ABOVE placement (id 5) counts → 1
    assert nashik_fte_placement_count_for_candidate(candidates[4], counts) == 1
