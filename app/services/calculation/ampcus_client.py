"""Ampcus Tech Client strategy — mark-up % slabs from incentive_slabs (MARKUP slab_type)."""

from decimal import Decimal
from typing import Any, Dict, List


def calculate_ampcus_client(
    *,
    candidate: Dict[str, Any],
    slabs: List[Any],
    recruiter_payable: bool,
) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    # Treat margin field as approved mark-up % when division is ampcusTechClient
    markup = candidate.get("margin")
    if markup is None:
        return lines
    markup = Decimal(str(markup))
    for s in slabs:
        if s.slab_type != "MARKUP":
            continue
        if s.margin_min is not None and markup < s.margin_min:
            continue
        if s.margin_max is not None and markup > s.margin_max:
            continue
        person_map = {
            "Recruiter": candidate.get("recruiter"),
            "Team Lead": candidate.get("team_lead"),
            "Manager": candidate.get("manager"),
            "CRM": candidate.get("crm"),
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
                "incentive_type": "RECURRING",
                "rule_applied": "ampcus_client.markup",
                "eligible": payable,
                "base_incentive": s.amount,
                "pro_rata_factor": Decimal("1"),
                "amount": s.amount if payable else Decimal("0"),
                "reason": "Approved mark-up slab",
            }
        )
    return lines
