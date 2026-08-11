from decimal import Decimal

from app.models.incentive_slab import IncentiveSlab
from app.services.calculation.nashik import calculate_nashik
from datetime import date


def _slab(**kwargs):
    defaults = dict(
        division="nashik",
        slab_type="MARGIN_RECURRING",
        role="Recruiter",
        amount=Decimal("1000"),
        effective_from=date.today(),
        is_active=True,
    )
    defaults.update(kwargs)
    return IncentiveSlab(**defaults)


def test_nashik_margin_recurring_prorata():
    slabs = [
        _slab(margin_min=Decimal("2.01"), margin_max=Decimal("4.0"), amount=Decimal("1000")),
        _slab(slab_type="TEAM_LEAD_RECURRING", role="Team Lead", amount=Decimal("250"), margin_min=None, margin_max=None),
    ]
    lines = calculate_nashik(
        candidate={
            "margin": Decimal("3.0"),
            "recruiter": "R1",
            "team_lead": "TL1",
        },
        hours=Decimal("80"),
        benchmark=Decimal("160"),
        slabs=slabs,
        project_ended_before_benchmark=False,
        recruiter_payable=True,
    )
    recruiter = next(l for l in lines if l["role"] == "Recruiter")
    assert recruiter["amount"] == Decimal("500.00")
    tl = next(l for l in lines if l["role"] == "Team Lead")
    assert tl["amount"] == Decimal("125.00")


def test_nashik_project_end_special():
    slabs = [_slab(slab_type="PROJECT_END_SPECIAL", amount=Decimal("2000"), margin_min=None, margin_max=None)]
    lines = calculate_nashik(
        candidate={"margin": Decimal("5"), "recruiter": "R1"},
        hours=Decimal("40"),
        benchmark=Decimal("160"),
        slabs=slabs,
        project_ended_before_benchmark=True,
        recruiter_payable=True,
    )
    assert len(lines) == 1
    assert lines[0]["amount"] == Decimal("2000")
    assert lines[0]["incentive_type"] == "SPECIAL"
