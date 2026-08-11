"""Pluggable strategy helpers — parameters come from incentive_slabs, not hardcoded branches."""

from decimal import Decimal
from typing import Optional


def pro_rata(amount: Decimal, hours: Decimal, benchmark: Decimal) -> tuple[Decimal, Decimal]:
    if benchmark <= 0:
        return amount, Decimal("1")
    factor = min(hours / benchmark, Decimal("1"))
    return (amount * factor).quantize(Decimal("0.01")), factor.quantize(Decimal("0.0001"))


def in_range(
    value: Optional[Decimal],
    low: Optional[Decimal],
    high: Optional[Decimal],
) -> bool:
    if value is None:
        return low is None and high is None
    if low is not None and value < low:
        return False
    if high is not None and value > high:
        return False
    return True
