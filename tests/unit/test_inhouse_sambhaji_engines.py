from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.cycles.engines.ampcus_inhouse import calculate_placement as inhouse
from app.services.cycles.engines.sambhaji_nagar import calculate_placement as sambhaji, matrix_amount


def candidate(**overrides):
    values = dict(id=1, candidate_name="C", start_date=date(2026, 1, 1), end_date=None, incentive_active=True, status="ACTIVE", placement_level="BELOW_MANAGER", recruiter="R", manager="M", center_head="CH", avp="AVP", team_lead="TL", senior_manager="SM", crm="CRM", associate_director="AD", margin=Decimal("10.01"))
    values.update(overrides)
    return SimpleNamespace(**values)


def test_inhouse_90_day_and_level_amounts():
    lines = inhouse(candidate(), cycle_end=date(2026, 5, 1), coordinators={})
    assert {line.role: line.amount for line in lines} == {"Recruiter": Decimal("3000"), "Manager": Decimal("500"), "Center Head": Decimal("1000")}
    below = inhouse(candidate(start_date=date(2026, 4, 1)), cycle_end=date(2026, 5, 1), coordinators={})
    assert all(line.amount == 0 and line.reason == "INHOUSE_90_DAY_REQUIREMENT_NOT_MET" for line in below)


def test_sambhaji_matrix_and_payment_gate():
    assert matrix_amount(Decimal("10.01"), Decimal("160")) == 7000
    pending = sambhaji(candidate(), hours=Decimal("80"), payment_status="PENDING", coordinators={})
    assert all(line.amount == 0 for line in pending)
    paid = sambhaji(candidate(), hours=Decimal("80"), payment_status="RECEIVED", coordinators={})
    assert paid[0].amount == Decimal("5000")
