from datetime import date
from decimal import Decimal

from app.models.incentive_slab import IncentiveSlab
from app.services.calculation.sambhaji import calculate_sambhaji


def test_sambhaji_matrix_lookup():
    slabs = [
        IncentiveSlab(
            division="sambhajiNagar",
            slab_type="MARGIN_HOURS_MATRIX",
            role="Recruiter",
            margin_min=Decimal("1"),
            margin_max=Decimal("3"),
            hours_min=Decimal("41"),
            hours_max=Decimal("80"),
            amount=Decimal("1000"),
            effective_from=date.today(),
            is_active=True,
        )
    ]
    lines = calculate_sambhaji(
        candidate={"margin": Decimal("2.5"), "recruiter": "R1"},
        hours=Decimal("60"),
        slabs=slabs,
        recruiter_payable=True,
    )
    assert len(lines) == 1
    assert lines[0]["amount"] == Decimal("1000")


def test_sambhaji_recruiter_not_payable():
    slabs = [
        IncentiveSlab(
            division="sambhajiNagar",
            slab_type="MARGIN_HOURS_MATRIX",
            role="Recruiter",
            margin_min=Decimal("1"),
            margin_max=Decimal("3"),
            hours_min=Decimal("0"),
            hours_max=Decimal("40"),
            amount=Decimal("500"),
            effective_from=date.today(),
            is_active=True,
        )
    ]
    lines = calculate_sambhaji(
        candidate={"margin": Decimal("2"), "recruiter": "R1"},
        hours=Decimal("20"),
        slabs=slabs,
        recruiter_payable=False,
    )
    assert lines[0]["eligible"] is False
    assert lines[0]["amount"] == Decimal("0")
