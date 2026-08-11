"""Sambhaji Nagar strategy: margin × hours absolute matrix from incentive_slabs."""

from decimal import Decimal
from typing import Any, Dict, List


def calculate_sambhaji(
    *,
    candidate: Dict[str, Any],
    hours: Decimal,
    slabs: List[Any],
    recruiter_payable: bool,
) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    margin = candidate.get("margin")
    if margin is None:
        return lines
    margin = Decimal(str(margin))

    matrix = [
        s
        for s in slabs
        if s.slab_type == "MARGIN_HOURS_MATRIX"
        and s.role == "Recruiter"
        and (s.margin_min is None or margin >= s.margin_min)
        and (s.margin_max is None or margin <= s.margin_max)
        and (s.hours_min is None or hours >= s.hours_min)
        and (s.hours_max is None or hours <= s.hours_max)
    ]
    if matrix:
        slab = matrix[0]
        lines.append(
            {
                "role": "Recruiter",
                "person": candidate.get("recruiter") or "",
                "incentive_type": "RECURRING",
                "rule_applied": "sambhaji.margin_hours_matrix",
                "eligible": recruiter_payable and bool(candidate.get("recruiter")),
                "base_incentive": slab.amount,
                "pro_rata_factor": Decimal("1"),
                "amount": slab.amount if recruiter_payable else Decimal("0"),
                "reason": "Margin × hours matrix",
            }
        )

    # Other role flat amounts if present as OTHER_ROLE slabs
    for s in slabs:
        if s.slab_type != "OTHER_ROLE":
            continue
        person_map = {
            "Team Lead": candidate.get("team_lead"),
            "Manager": candidate.get("manager"),
            "Senior Manager": candidate.get("senior_manager"),
            "CRM": candidate.get("crm"),
            "Associate Director": candidate.get("associate_director"),
            "Center Head": candidate.get("center_head"),
        }
        person = person_map.get(s.role)
        if not person:
            continue
        lines.append(
            {
                "role": s.role,
                "person": person,
                "incentive_type": "RECURRING",
                "rule_applied": "sambhaji.other_role",
                "eligible": True,
                "base_incentive": s.amount,
                "pro_rata_factor": Decimal("1"),
                "amount": s.amount,
                "reason": "Other role amount",
            }
        )
    return lines
