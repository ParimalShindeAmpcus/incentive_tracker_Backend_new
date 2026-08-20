from datetime import date
from decimal import Decimal

from app.services.incentives.nashik_calculator import CycleWindow, PlacementInput, calculate_nashik_placement
from app.services.incentives.nashik_rules import nashik_pro_rata, nashik_recruiter_base


def _placement(**kwargs) -> PlacementInput:
    data = dict(
        candidate_pk=1,
        external_id="ND-1",
        name="Example",
        contract_type="W2",
        candidate_source="Ampcus Inc",
        organization="Ampcus Inc",
        recruiter_location="Nashik",
        start_date=date(2026, 6, 1),
        end_date=None,
        margin=Decimal("8"),
        hours=Decimal("160"),
        recruiter="Ria Recruiter",
        team_lead="Tara Lead",
        crm="Cara CRM",
        manager="Mina Manager",
        senior_manager=None,
        associate_director=None,
        center_head=None,
        avp=None,
        incentive_active=True,
        project_ended=False,
    )
    data.update(kwargs)
    return PlacementInput(**data)


WINDOW = CycleWindow(start=date(2026, 7, 1), end=date(2026, 7, 31))


def _amount(lines, role: str) -> Decimal:
    return sum((line.amount for line in lines if line.role == role and line.eligible), Decimal("0"))


def test_slab_boundaries():
    cases = [
        (Decimal("0"), "special", Decimal("2000")),
        (Decimal("0.99"), "special", Decimal("2000")),
        (Decimal("1"), "slab", Decimal("500")),
        (Decimal("2"), "slab", Decimal("500")),
        (Decimal("2.01"), "slab", Decimal("1000")),
        (Decimal("4"), "slab", Decimal("1000")),
        (Decimal("4.01"), "slab", Decimal("1500")),
        (Decimal("6"), "slab", Decimal("1500")),
        (Decimal("6.01"), "slab", Decimal("2000")),
        (Decimal("8"), "slab", Decimal("2000")),
        (Decimal("8.01"), "slab", Decimal("2500")),
        (Decimal("10"), "slab", Decimal("2500")),
        (Decimal("10.01"), "slab", Decimal("3500")),
        (Decimal("15"), "slab", Decimal("3500")),
        (Decimal("15.01"), "slab", Decimal("4000")),
        (Decimal("20"), "slab", Decimal("4000")),
        (Decimal("20.01"), "slab", Decimal("4500")),
        (Decimal("30"), "slab", Decimal("4500")),
        (Decimal("30.01"), "slab", Decimal("7000")),
        (Decimal("40"), "slab", Decimal("7000")),
        (Decimal("40.01"), "slab", Decimal("10000")),
        (Decimal("50"), "slab", Decimal("10000")),
    ]
    for margin, kind, base in cases:
        got_kind, got_base, _ = nashik_recruiter_base(margin)
        assert got_kind == kind, margin
        assert got_base == base, margin


def test_recruiter_160_hours():
    lines = calculate_nashik_placement(_placement(hours=Decimal("160")), WINDOW)
    assert _amount(lines, "Recruiter") == Decimal("2000")


def test_recruiter_prorata_80_hours():
    lines = calculate_nashik_placement(_placement(hours=Decimal("80")), WINDOW)
    assert _amount(lines, "Recruiter") == Decimal("1000")
    assert nashik_pro_rata(Decimal("2000"), Decimal("80"))[1] == Decimal("1000")


def test_team_lead_prorata():
    lines = calculate_nashik_placement(_placement(hours=Decimal("80")), WINDOW)
    assert _amount(lines, "Team Lead") == Decimal("125")


def test_leadership_not_prorated_below_160():
    lines = calculate_nashik_placement(_placement(hours=Decimal("80")), WINDOW)
    assert _amount(lines, "CRM") == Decimal("0")
    assert _amount(lines, "Manager") == Decimal("0")


def test_leadership_after_160():
    lines = calculate_nashik_placement(_placement(hours=Decimal("160")), WINDOW)
    assert _amount(lines, "CRM") == Decimal("1000")
    assert _amount(lines, "Manager") == Decimal("1500")


def test_low_margin_one_time():
    lines = calculate_nashik_placement(_placement(margin=Decimal("0.99")), WINDOW)
    rec = next(line for line in lines if line.role == "Recruiter")
    assert rec.incentive_type == "SPECIAL"
    assert rec.amount == Decimal("2000")


def test_duplicate_special_blocked():
    first = calculate_nashik_placement(_placement(margin=Decimal("0.99")), WINDOW)
    key = next(line.paid_key() for line in first if line.role == "Recruiter")
    second = calculate_nashik_placement(_placement(margin=Decimal("0.99")), WINDOW, {key})
    rec = next(line for line in second if line.role == "Recruiter")
    assert rec.amount == Decimal("0")
    assert rec.eligible is False


def test_max_two_roles_per_person_includes_recruiter():
    lines = calculate_nashik_placement(
        _placement(recruiter="Alex", team_lead="Alex", crm="Alex", manager="Alex"),
        WINDOW,
    )
    alex = [line for line in lines if line.person == "Alex" and line.eligible and line.amount > 0]
    assert len(alex) == 2
    roles = {line.role for line in alex}
    assert roles == {"Manager", "CRM"}
    assert "Recruiter" not in roles


def test_client_name_is_not_blocking_company():
    lines = calculate_nashik_placement(
        _placement(candidate_source="Acme Healthcare", organization="Acme Healthcare"),
        WINDOW,
    )
    rec = next(line for line in lines if line.role == "Recruiter")
    assert rec.amount == Decimal("2000")


def test_non_w2_c2c_excluded():
    lines = calculate_nashik_placement(_placement(contract_type="1099"), WINDOW)
    assert all(not line.eligible or line.amount == 0 for line in lines)
