from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.cycles.engines.ampcus_client import calculate_placement, resolve_slab


def placement(**overrides):
    values = dict(
        id=1, candidate_name="Candidate", start_date=date(2026, 8, 1), end_date=None,
        ownership_confirmed=True, incentive_active=True, status="ACTIVE",
        approved_markup_percentage=Decimal("18.50"), recruiter="Recruiter", team_lead="Lead",
        manager="Manager", crm="CRM", center_head="Center Head", avp="AVP",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def payment(status="RECEIVED"):
    return SimpleNamespace(status=status, payment_received_date=date(2026, 9, 5), payment_reference="INV-1")


def amounts(lines):
    return {line.role: line.amount for line in lines}


def test_normal_client_placement_uses_approved_markup_and_center_head():
    lines = calculate_placement(placement(), cycle_end=date(2026, 8, 31), payment=payment())
    assert amounts(lines) == {
        "Recruiter": Decimal("5000"), "Team Lead": Decimal("500"), "Manager": Decimal("1000"),
        "CRM": Decimal("1000"), "CH/VP": Decimal("1500"),
    }
    assert next(line for line in lines if line.role == "CH/VP").person == "Center Head"


def test_ch_vp_falls_back_to_avp_without_double_payment():
    lines = calculate_placement(placement(center_head=None), cycle_end=date(2026, 8, 31), payment=payment())
    assert len(lines) == 5
    assert next(line for line in lines if line.role == "CH/VP").person == "AVP"


def test_boundaries_follow_open_lower_closed_upper_rules():
    assert resolve_slab(Decimal("5"))[2]["Recruiter"] == 0
    assert resolve_slab(Decimal("10"))[2]["Recruiter"] == 2000
    assert resolve_slab(Decimal("15"))[2]["Recruiter"] == 3000
    assert resolve_slab(Decimal("20"))[2]["Recruiter"] == 5000
    assert resolve_slab(Decimal("40"))[2]["Recruiter"] == 9000
    assert resolve_slab(Decimal("45"))[2]["Recruiter"] == 10000


def test_inactive_and_payment_pending_zero_every_role():
    inactive = calculate_placement(placement(status="INACTIVE"), cycle_end=date(2026, 8, 31), payment=payment())
    assert all(line.amount == 0 and line.reason == "CANDIDATE_INACTIVE" for line in inactive)
    pending = calculate_placement(placement(), cycle_end=date(2026, 8, 31), payment=payment("PENDING"))
    assert all(line.amount == 0 and line.reason == "PAYMENT_PENDING" for line in pending)


def test_left_recruiter_does_not_block_hierarchy():
    left = SimpleNamespace(employment_status="LEFT")
    lines = calculate_placement(
        placement(), cycle_end=date(2026, 8, 31), payment=payment(), coordinators={"recruiter": left},
    )
    assert next(line for line in lines if line.role == "Recruiter").amount == 0
    assert next(line for line in lines if line.role == "Team Lead").amount == 500
