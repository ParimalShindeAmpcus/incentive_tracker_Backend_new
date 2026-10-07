"""Ampcus client placement markup policy, in INR.

Exactly 5% belongs to the nil band, per the eligibility guidelines.
"""
from decimal import Decimal

PAYOUT_ROLES = ("Recruiter", "Team Lead", "Manager", "CRM", "CH/VP")
ELIGIBILITY = (
    "First full month payment received from client; approved placement markup; "
    "candidate has started assignment; placement ownership confirmed. "
    "Markup from 0% through 5% has no incentive payout."
)
MARKUP_SLABS = tuple(
    (Decimal(low), Decimal(high), {
        **dict(zip(PAYOUT_ROLES, amounts)),
        "Center Head": amounts[4],
        "AVP": amounts[4],
    })
    for low, high, amounts in (
        ("0", "5.00", (0, 0, 0, 0, 0)),
        ("5.00", "10.00", (2000, 250, 500, 750, 500)),
        ("10.01", "15.00", (3000, 250, 500, 750, 1000)),
        ("15.01", "20.00", (5000, 500, 1000, 1000, 1500)),
        ("20.01", "25.00", (6000, 500, 1000, 1500, 2000)),
        ("25.01", "30.00", (7000, 500, 1000, 1500, 2500)),
        ("30.01", "35.00", (8000, 500, 1000, 1500, 3000)),
        ("35.01", "40.00", (9000, 500, 1000, 1500, 3500)),
        ("40.01", "100.00", (10000, 500, 1000, 1500, 4000)),
    )
)


def calculation_payouts(payouts):
    """Resolve existing candidate hierarchy names to the policy's rate groups."""
    result = dict(payouts)
    if "Manager" in payouts:
        result.setdefault("Senior Manager", payouts["Manager"])
    if "CH/VP" in payouts:
        for role in ("Associate Director", "Center Head", "AVP", "Director"):
            result.setdefault(role, payouts["CH/VP"])
    return result
