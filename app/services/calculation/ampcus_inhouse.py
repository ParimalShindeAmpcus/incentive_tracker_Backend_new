"""Ampcus Tech In-House strategy — flat amounts after tenure from INHOUSE slabs."""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional


def calculate_ampcus_inhouse(
    *,
    candidate: Dict[str, Any],
    slabs: List[Any],
    as_of: Optional[date] = None,
    recruiter_payable: bool,
) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    as_of = as_of or date.today()
    start = candidate.get("start_date")
    if not start:
        return lines
    days = (as_of - start).days
    for s in slabs:
        if s.slab_type != "INHOUSE":
            continue
        if s.hours_min is not None and Decimal(days) < s.hours_min:
            continue
        person_map = {
            "Recruiter": candidate.get("recruiter"),
            "Manager": candidate.get("manager"),
            "Center Head": candidate.get("center_head"),
        }
        person = person_map.get(s.role)
        if not person:
            continue
        payable = recruiter_payable if s.role == "Recruiter" else True
        lines.append(
            {
                "role": s.role,
                "person": person,
                "incentive_type": "ONETIME",
                "rule_applied": "ampcus_inhouse.flat",
                "eligible": payable,
                "base_incentive": s.amount,
                "pro_rata_factor": Decimal("1"),
                "amount": s.amount if payable else Decimal("0"),
                "reason": f"Inhouse after {days} days",
            }
        )
    return lines
