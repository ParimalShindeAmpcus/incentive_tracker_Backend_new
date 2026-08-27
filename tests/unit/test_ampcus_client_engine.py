from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.cycles.engines.ampcus_client import calculate_placement, resolve_slab


def placement(**overrides):
    values = dict(
        id=1, candidate_name="Candidate", start_date=date(2026, 8, 1), end_date=None,
        ownership_confirmed=True, incentive_active=True, status="ACTIVE",
        approved_markup_percentage=Decimal("18.50"), margin=Decimal("18.50"), recruiter="Recruiter", team_lead="Lead",
        manager="Manager", crm="CRM", center_head="Center Head", avp=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def payment(status="RECEIVED"):
    return SimpleNamespace(status=status, payment_received_date=date(2026, 9, 5), payment_reference="INV-1")


def amounts(lines):
    return {line.role: line.amount for line in lines}


def active_coordinators(*names):
    return {name.lower().strip(): SimpleNamespace(employment_status="ACTIVE") for name in names}


def test_normal_client_placement_uses_approved_markup_and_center_head():
    coords = active_coordinators("Recruiter", "Lead", "Manager", "CRM", "Center Head")
    lines = calculate_placement(placement(), cycle_end=date(2026, 8, 31), payment=payment(), coordinators=coords)
    assert amounts(lines) == {
        "Recruiter": Decimal("5000"), "Team Lead": Decimal("500"), "Manager": Decimal("1000"),
        "CRM": Decimal("1000"), "Center Head": Decimal("1500"),
    }
    assert next(line for line in lines if line.role == "Center Head").person == "Center Head"


def test_senior_manager_same_as_manager():
    coords = active_coordinators("Recruiter", "Lead", "Sr Mgr", "CRM", "Center Head")
    # Placement with Senior Manager instead of Manager
    lines = calculate_placement(
        placement(manager=None, senior_manager="Sr Mgr"),
        cycle_end=date(2026, 8, 31),
        payment=payment(),
        coordinators=coords,
    )
    assert next(line for line in lines if line.role == "Senior Manager").amount == Decimal("1000")
    assert next(line for line in lines if line.role == "Senior Manager").eligible is True

    # Placement with both Manager and Senior Manager
    coords_both = active_coordinators("Recruiter", "Lead", "Manager", "Sr Mgr", "CRM", "Center Head")
    lines_both = calculate_placement(
        placement(manager="Manager", senior_manager="Sr Mgr"),
        cycle_end=date(2026, 8, 31),
        payment=payment(),
        coordinators=coords_both,
    )
    assert next(line for line in lines_both if line.role == "Manager").amount == Decimal("1000")
    assert next(line for line in lines_both if line.role == "Senior Manager").amount == Decimal("1000")


def test_associate_director_center_head_vp_avp_same_incentive():
    coords = active_coordinators("Recruiter", "Lead", "Manager", "CRM", "AD", "CH", "VP Person", "AVP Person")
    lines = calculate_placement(
        placement(
            center_head="CH",
            associate_director="AD",
            director="VP Person",
            avp="AVP Person",
        ),
        cycle_end=date(2026, 8, 31),
        payment=payment(),
        coordinators=coords,
    )
    # All four leadership roles get the exact same tier incentive (1500 at 18.5% markup)
    ad_line = next(line for line in lines if line.role == "Associate Director")
    ch_line = next(line for line in lines if line.role == "Center Head")
    vp_line = next(line for line in lines if line.role == "Director")
    avp_line = next(line for line in lines if line.role == "AVP")

    assert ad_line.amount == Decimal("1500") and ad_line.eligible is True
    assert ch_line.amount == Decimal("1500") and ch_line.eligible is True
    assert vp_line.amount == Decimal("1500") and vp_line.eligible is True
    assert avp_line.amount == Decimal("1500") and avp_line.eligible is True


def test_ch_vp_falls_back_to_avp():
    coords = active_coordinators("Recruiter", "Lead", "Manager", "CRM", "AVP")
    lines = calculate_placement(placement(center_head=None, avp="AVP"), cycle_end=date(2026, 8, 31), payment=payment(), coordinators=coords)
    assert len(lines) == 5
    assert next(line for line in lines if line.role == "AVP").person == "AVP"
    assert next(line for line in lines if line.role == "AVP").amount == Decimal("1500")


def test_boundaries_follow_open_lower_closed_upper_rules():
    assert resolve_slab(Decimal("4.9"))[2]["Recruiter"] == 0
    assert resolve_slab(Decimal("5"))[2]["Recruiter"] == 2000
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
    coords = active_coordinators("Lead", "Manager", "CRM", "Center Head", "AVP")
    coords["recruiter"] = SimpleNamespace(employment_status="LEFT")
    lines = calculate_placement(
        placement(), cycle_end=date(2026, 8, 31), payment=payment(), coordinators=coords,
    )
    assert next(line for line in lines if line.role == "Recruiter").amount == 0
    assert next(line for line in lines if line.role == "Team Lead").amount == 500


def test_missing_role_does_not_exclude_entire_placement():
    # If CRM is missing (None), it should get 0 (MISSING_HIERARCHY), but others should still get paid.
    coords = active_coordinators("Recruiter", "Lead", "Manager", "Center Head", "AVP")
    lines = calculate_placement(
        placement(crm=None), cycle_end=date(2026, 8, 31), payment=payment(), coordinators=coords,
    )
    assert len(lines) == 5
    assert next(line for line in lines if line.role == "CRM").amount == 0
    assert next(line for line in lines if line.role == "CRM").reason == "MISSING_HIERARCHY"
    # Recruiter and Manager should still get paid
    assert next(line for line in lines if line.role == "Recruiter").amount == 5000
    assert next(line for line in lines if line.role == "Manager").amount == 1000


def test_max_two_roles_enforcement():
    # Bob holds Team Lead, Manager, and CRM (3 leadership roles).
    # Since Bob holds 3 roles, only the 2 highest priority ones (CRM, Manager) should be allowed.
    # Team Lead should be excluded (ROLE_LIMIT_EXCEEDED).
    # Recruiter (Alice) and Center Head (Charlie) should be unaffected.
    coords = active_coordinators("Alice", "Bob", "Charlie")
    lines = calculate_placement(
        placement(recruiter="Alice", team_lead="Bob", manager="Bob", crm="Bob", center_head="Charlie"),
        cycle_end=date(2026, 8, 31),
        payment=payment(),
        coordinators=coords,
    )
    # Check eligibility and reasons
    rec_line = next(line for line in lines if line.role == "Recruiter")
    tl_line = next(line for line in lines if line.role == "Team Lead")
    mgr_line = next(line for line in lines if line.role == "Manager")
    crm_line = next(line for line in lines if line.role == "CRM")
    ch_line = next(line for line in lines if line.role in {"Center Head", "CH/VP"})

    assert rec_line.eligible is True
    assert rec_line.amount == 5000

    assert tl_line.eligible is False
    assert tl_line.reason == "ROLE_LIMIT_EXCEEDED"
    assert tl_line.amount == 0

    assert mgr_line.eligible is True
    assert mgr_line.amount == 1000

    assert crm_line.eligible is True
    assert crm_line.amount == 1000

    assert ch_line.eligible is True
    assert ch_line.amount == 1500


def test_max_two_roles_enforcement_with_recruiter():
    # Sneha Nair holds Recruiter, Team Lead, and Manager (3 roles total, including Recruiter).
    # Since Sneha holds 3 roles, only the 2 highest priority ones (Recruiter, Manager) should be allowed.
    # Team Lead should be excluded (ROLE_LIMIT_EXCEEDED).
    # CRM (Not Applicable) and Center Head (Not Applicable) should be unaffected.
    coords = active_coordinators("Sneha Nair")
    lines = calculate_placement(
        placement(recruiter="Sneha Nair", team_lead="Sneha Nair", manager="Sneha Nair", crm="Not Applicable", center_head="Not Applicable"),
        cycle_end=date(2026, 8, 31),
        payment=payment(),
        coordinators=coords,
    )
    rec_line = next(line for line in lines if line.role == "Recruiter")
    tl_line = next(line for line in lines if line.role == "Team Lead")
    mgr_line = next(line for line in lines if line.role == "Manager")
    crm_line = next(line for line in lines if line.role == "CRM")
    ch_line = next(line for line in lines if line.role in {"Center Head", "CH/VP"})

    assert rec_line.eligible is True
    assert rec_line.amount == 5000

    assert tl_line.eligible is False
    assert tl_line.reason == "ROLE_LIMIT_EXCEEDED"
    assert tl_line.amount == 0

    assert mgr_line.eligible is True
    assert mgr_line.amount == 1000

    assert crm_line.eligible is False
    assert crm_line.reason == "ROLE_NOT_APPLICABLE"

    assert ch_line.eligible is False
    assert ch_line.reason == "ROLE_NOT_APPLICABLE"


def test_already_paid_duplicate_prevention():
    # Candidate ID 1 has already been paid for Recruiter and CRM.
    # When calculating placement for Candidate 1, Recruiter and CRM should be excluded as ALREADY_PAID,
    # but other roles (Team Lead, Manager, Center Head) should still be processed normally.
    coords = active_coordinators("Recruiter", "Lead", "Manager", "CRM", "Center Head")
    paid = {
        "1|AMPCUS_CLIENT_MARKUP|Recruiter|recruiter",
        "1|AMPCUS_CLIENT_MARKUP|CRM|crm",
    }
    lines = calculate_placement(
        placement(),
        cycle_end=date(2026, 8, 31),
        payment=payment(),
        coordinators=coords,
        paid_keys=paid,
    )
    rec_line = next(line for line in lines if line.role == "Recruiter")
    tl_line = next(line for line in lines if line.role == "Team Lead")
    mgr_line = next(line for line in lines if line.role == "Manager")
    crm_line = next(line for line in lines if line.role == "CRM")
    ch_line = next(line for line in lines if line.role in {"Center Head", "CH/VP"})

    assert rec_line.eligible is False
    assert rec_line.reason == "ALREADY_PAID"
    assert rec_line.amount == 0

    assert crm_line.eligible is False
    assert crm_line.reason == "ALREADY_PAID"
    assert crm_line.amount == 0

    assert tl_line.eligible is True
    assert tl_line.amount == 500

    assert mgr_line.eligible is True
    assert mgr_line.amount == 1000

    assert ch_line.eligible is True
    assert ch_line.amount == 1500


def test_missing_center_head_from_recruiter_master_exempts_only_that_role():
    coords = active_coordinators("Recruiter", "Lead", "Manager", "CRM")  # Center Head / AVP absent
    lines = calculate_placement(placement(), cycle_end=date(2026, 8, 31), payment=payment(), coordinators=coords)
    rec = next(line for line in lines if line.role == "Recruiter")
    tl = next(line for line in lines if line.role == "Team Lead")
    mgr = next(line for line in lines if line.role == "Manager")
    crm = next(line for line in lines if line.role == "CRM")
    ch = next(line for line in lines if line.role in {"Center Head", "CH/VP"})
    assert rec.eligible is True and rec.amount == Decimal("5000")
    assert tl.eligible is True and tl.amount == Decimal("500")
    assert mgr.eligible is True and mgr.amount == Decimal("1000")
    assert crm.eligible is True and crm.amount == Decimal("1000")
    assert ch.eligible is False
    assert ch.reason == "EXEMPTED_MISSING_RECRUITER_MASTER"
    assert ch.amount == Decimal("0")


def test_left_and_notice_in_recruiter_master_are_not_treated_as_missing():
    coords = active_coordinators("Recruiter", "Lead", "Manager", "CRM", "Center Head")
    coords["lead"] = SimpleNamespace(employment_status="NOTICE")
    coords["manager"] = SimpleNamespace(employment_status="LEFT")
    lines = calculate_placement(placement(), cycle_end=date(2026, 8, 31), payment=payment(), coordinators=coords)
    assert next(line for line in lines if line.role == "Team Lead").reason == "COORDINATOR_ON_NOTICE"
    assert next(line for line in lines if line.role == "Manager").reason == "COORDINATOR_LEFT"
    assert next(line for line in lines if line.role == "Recruiter").reason == "ELIGIBLE"
    assert next(line for line in lines if line.role in {"Center Head", "CH/VP"}).reason == "ELIGIBLE"
