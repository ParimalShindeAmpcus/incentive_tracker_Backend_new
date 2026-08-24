from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.cycles.engines.ampcus_inhouse import calculate_placement as inhouse
from app.services.cycles.engines.sambhaji_nagar import calculate_placement as sambhaji, matrix_amount


def candidate(**overrides):
    values = dict(
        id=1,
        candidate_name="C",
        start_date=date(2026, 1, 1),
        end_date=None,
        incentive_active=True,
        status="ACTIVE",
        placement_level="BELOW_MANAGER",
        recruiter="R",
        manager="M",
        center_head="CH",
        avp="AVP",
        team_lead="TL",
        senior_manager="SM",
        crm="CRM",
        associate_director="AD",
        margin=Decimal("10.01"),
        organization="Ampcus Inc",
        candidate_source="Ampcus Inc",
        recruiter_location="Sambhaji Nagar",
        contract_type="C2C",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _mock_coordinators(*names, status="ACTIVE"):
    """Build a coordinator index with given names, all with the same status."""
    coords = {}
    for name in names:
        coords[name.strip().lower()] = SimpleNamespace(
            normalized_name=name, employment_status=status, is_deleted=False,
        )
    return coords


def _active_coordinators():
    """Default coordinator index matching candidate() default hierarchy."""
    return _mock_coordinators("R", "M", "CH")


def test_inhouse_90_day_and_level_amounts():
    coords = _active_coordinators()
    lines = inhouse(candidate(), cycle_end=date(2026, 5, 1), coordinators=coords)
    assert {line.role: line.amount for line in lines} == {"Recruiter": Decimal("3000"), "Manager": Decimal("500"), "Center Head": Decimal("1000")}
    assert all(line.eligible is True and line.reason == "ELIGIBLE" for line in lines)

    # Above manager level
    above = inhouse(candidate(placement_level="ABOVE_MANAGER"), cycle_end=date(2026, 5, 1), coordinators=coords)
    assert {line.role: line.amount for line in above} == {"Recruiter": Decimal("5000"), "Manager": Decimal("500"), "Center Head": Decimal("1000")}

    # Less than 90 days tenure
    below = inhouse(candidate(start_date=date(2026, 4, 1)), cycle_end=date(2026, 5, 1), coordinators=coords)
    assert all(line.amount == 0 and line.eligible is False and line.reason == "INHOUSE_90_DAY_REQUIREMENT_NOT_MET" for line in below)

    # Already paid deduplication
    paid_keys = {"1|INHOUSE|Recruiter|r", "1|INHOUSE|Manager|m"}
    dedup = inhouse(candidate(), cycle_end=date(2026, 5, 1), coordinators=coords, paid_keys=paid_keys)
    assert {line.role: (line.amount, line.reason) for line in dedup} == {
        "Recruiter": (Decimal("0"), "ALREADY_PAID"),
        "Manager": (Decimal("0"), "ALREADY_PAID"),
        "Center Head": (Decimal("1000"), "ELIGIBLE"),
    }


def test_inhouse_coordinator_status_all_roles():
    """C1: Coordinator LEFT/NOTICE should exclude ALL roles, not just Recruiter."""
    # Manager has LEFT status
    coords = {
        "r": SimpleNamespace(normalized_name="R", employment_status="ACTIVE", is_deleted=False),
        "m": SimpleNamespace(normalized_name="M", employment_status="LEFT", is_deleted=False),
        "ch": SimpleNamespace(normalized_name="CH", employment_status="NOTICE", is_deleted=False),
    }
    lines = inhouse(candidate(), cycle_end=date(2026, 5, 1), coordinators=coords)
    result = {line.role: line.reason for line in lines}
    assert result["Recruiter"] == "ELIGIBLE"
    assert result["Manager"] == "COORDINATOR_LEFT"
    assert result["Center Head"] == "COORDINATOR_ON_NOTICE"


def test_inhouse_per_role_hierarchy_exclusion():
    """C2: Only the missing role should be excluded, not all roles."""
    coords = _active_coordinators()
    c = candidate(manager=None)  # Manager is missing
    lines = inhouse(c, cycle_end=date(2026, 5, 1), coordinators=coords)
    result = {line.role: (line.reason, line.amount) for line in lines}
    assert result["Manager"] == ("MISSING_HIERARCHY", Decimal("0"))
    assert result["Recruiter"] == ("ELIGIBLE", Decimal("3000"))
    assert result["Center Head"] == ("ELIGIBLE", Decimal("1000"))


def test_inhouse_max_two_roles():
    """W1: If one person holds 3+ roles, only top 2 payouts are kept."""
    # Same person for all 3 roles
    coords = _mock_coordinators("Same Person")
    c = candidate(recruiter="Same Person", manager="Same Person", center_head="Same Person")
    lines = inhouse(c, cycle_end=date(2026, 5, 1), coordinators=coords)
    result = {line.role: line.reason for line in lines}
    # Recruiter(3000) and Center Head(1000) kept, Manager(500) excluded
    assert result["Recruiter"] == "ELIGIBLE"
    assert result["Center Head"] == "ELIGIBLE"
    assert result["Manager"] == "EXCEEDED_MAX_ROLES"


def test_inhouse_absconded_status():
    """W2: ABSCONDED status should be caught."""
    coords = _active_coordinators()
    c = candidate(status="Absconded")
    lines = inhouse(c, cycle_end=date(2026, 5, 1), coordinators=coords)
    assert all(line.reason == "CANDIDATE_INACTIVE" for line in lines)


def test_inhouse_coordinator_not_in_master():
    """W3: Coordinator not found in master should be flagged."""
    coords = _mock_coordinators("R", "CH")  # Manager "M" is missing from coordinator master
    lines = inhouse(candidate(), cycle_end=date(2026, 5, 1), coordinators=coords)
    result = {line.role: line.reason for line in lines}
    assert result["Recruiter"] == "ELIGIBLE"
    assert result["Manager"] == "EXEMPTED_MISSING_RECRUITER_MASTER"
    assert result["Center Head"] == "ELIGIBLE"


def test_inhouse_inactive_status_in_master_is_not_missing():
    """Inactive in Recruiter Master still counts as present; existing status rules apply."""
    coords = {
        "r": SimpleNamespace(normalized_name="R", employment_status="INACTIVE", is_deleted=False),
        "m": SimpleNamespace(normalized_name="M", employment_status="ACTIVE", is_deleted=False),
        "ch": SimpleNamespace(normalized_name="CH", employment_status="ACTIVE", is_deleted=False),
    }
    lines = inhouse(candidate(), cycle_end=date(2026, 5, 1), coordinators=coords)
    result = {line.role: (line.reason, line.eligible, line.amount) for line in lines}
    assert result["Recruiter"][0] == "ELIGIBLE"
    assert result["Recruiter"][1] is True
    assert result["Manager"][0] == "ELIGIBLE"


def test_sambhaji_matrix_and_payment_gate():
    coords = _mock_coordinators("R", "M", "CH", "AVP", "TL", "SM", "CRM", "AD")
    assert matrix_amount(Decimal("10.01"), Decimal("160")) == 7000
    pending = sambhaji(candidate(), hours=Decimal("80"), payment_status="PENDING", coordinators=coords)
    assert all(line.amount == 0 for line in pending)
    paid = sambhaji(candidate(), hours=Decimal("80"), payment_status="RECEIVED", coordinators=coords)
    assert paid[0].amount == Decimal("5000")


def test_sambhaji_missing_center_head_exempts_only_that_role():
    coords = _mock_coordinators("R", "M", "AVP", "TL", "SM", "CRM", "AD")  # CH missing
    lines = sambhaji(candidate(), hours=Decimal("160"), payment_status="RECEIVED", coordinators=coords)
    by_role = {line.role: line for line in lines}
    assert by_role["Recruiter"].eligible is True
    assert by_role["Recruiter"].amount == Decimal("7000")
    assert by_role["Center Head"].eligible is False
    assert by_role["Center Head"].reason == "EXEMPTED_MISSING_RECRUITER_MASTER"
    assert by_role["Manager"].eligible is True


