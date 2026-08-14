"""Nashik Division incentive formulas (mirrors frontend incentiveRules.ts)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

NASHIK_DIVISION_KEYS = {"nashik", "nd"}
NASHIK_CONTRACT_TYPES = {"W2", "C2C"}
NASHIK_COMPANIES = ("Ampcus Inc", "Bravens Inc", "Apokrin LLC", "BravensTech")
STANDARD_HOURS = Decimal("160")
LOW_MARGIN_THRESHOLD = Decimal("1.00")
LOW_MARGIN_ONE_TIME = Decimal("2000")
TEAM_LEAD_BASE = Decimal("250")
PROJECT_END_RECRUITER = Decimal("2000")
MAX_ROLES_PER_PERSON = 2

# Inclusive [min, max] USD/hour → 160-hour recruiter incentive INR
RECRUITER_SLABS: List[Tuple[Decimal, Decimal, Decimal]] = [
    (Decimal("1.00"), Decimal("2.00"), Decimal("500")),
    (Decimal("2.01"), Decimal("4.00"), Decimal("1000")),
    (Decimal("4.01"), Decimal("6.00"), Decimal("1500")),
    (Decimal("6.01"), Decimal("8.00"), Decimal("2000")),
    (Decimal("8.01"), Decimal("10.00"), Decimal("2500")),
    (Decimal("10.01"), Decimal("15.00"), Decimal("3500")),
    (Decimal("15.01"), Decimal("20.00"), Decimal("4000")),
    (Decimal("20.01"), Decimal("30.00"), Decimal("4500")),
    (Decimal("30.01"), Decimal("40.00"), Decimal("7000")),
    (Decimal("40.01"), Decimal("50.00"), Decimal("10000")),
]

LEADERSHIP_ONE_TIME = {
    "CRM": Decimal("1000"),
    "Manager": Decimal("1500"),
    "Senior Manager": Decimal("1500"),
    "Associate Director": Decimal("1750"),
    "Center Head": Decimal("1500"),
    "AVP": Decimal("2300"),
}

# Highest priority first — used when one person holds multiple roles
ROLE_PRIORITY = [
    "AVP",
    "Associate Director",
    "Senior Manager",
    "Center Head",
    "Manager",
    "CRM",
    "Team Lead",
]


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rounded_margin(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def nashik_recruiter_base(margin: Decimal) -> Tuple[str, Decimal, str]:
    """Return (kind, base, category) where kind is special|slab|none."""
    v = rounded_margin(margin)
    if v < LOW_MARGIN_THRESHOLD:
        return "special", LOW_MARGIN_ONE_TIME, "<= $0.99"
    for lo, hi, amount in RECRUITER_SLABS:
        if lo <= v <= hi:
            return "slab", amount, f"${lo} – ${hi}"
    return "none", Decimal("0"), "outside slabs"


def nashik_pro_rata(base: Decimal, hours: Decimal) -> Tuple[Decimal, Decimal]:
    if hours >= STANDARD_HOURS:
        return Decimal("1"), money(base)
    factor = money(hours / STANDARD_HOURS)
    return factor, money(base * factor)


def _compact(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _classify_company(value: Optional[str]) -> str:
    v = _compact(value or "")
    if not v:
        return "unknown"
    if "ampcustech" in v or "inhouse" in v or v == "itech":
        return "other"
    if "apokrin" in v or "bravens" in v or "ampcus" in v:
        return "nashik"
    return "unknown"


def matches_nashik_company(source: Optional[str], organization: Optional[str]) -> bool:
    kinds = [
        kind
        for kind in (_classify_company(organization), _classify_company(source))
        if kind != "unknown"
    ]
    if not kinds:
        return True
    if "nashik" in kinds:
        return True
    return not all(kind == "other" for kind in kinds)


def is_nashik_office(recruiter_location: Optional[str]) -> bool:
    loc = (recruiter_location or "").strip().lower()
    if not loc:
        return True
    if "nashik" in loc or loc == "nd" or " nd" in f" {loc} ":
        return True
    blocked = ("sambhaji", "aurangabad", "pune", "hyderabad", "chennai", "bangalore", "bengaluru", "mumbai")
    return not any(token in loc for token in blocked)


def is_nashik_division(code: Optional[str]) -> bool:
    return (code or "").strip().lower() in NASHIK_DIVISION_KEYS


def normalize_contract(value: Optional[str]) -> str:
    return (value or "").strip().upper().replace(" ", "")


def normalize_person(value: Optional[str]) -> str:
    return " ".join((value or "").split()).strip().lower()
