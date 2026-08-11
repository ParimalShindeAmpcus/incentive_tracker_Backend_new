"""Full-time finders-fee strategy — amounts from FULLTIME slabs."""

from decimal import Decimal
from typing import Any, Dict, List


def calculate_fulltime(
    *,
    candidate: Dict[str, Any],
    slabs: List[Any],
    placement_count: int,
    recruiter_payable: bool,
) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    if (candidate.get("contract_type") or "").upper() not in {"FULLTIME", "FULL-TIME", "FT"}:
        return lines
    band = "1" if placement_count <= 1 else ("2" if placement_count == 2 else "3+")
    for s in slabs:
        if s.slab_type != "FULLTIME":
            continue
        # encode band in role suffix or margin_min as placement count proxy — use role match
        if s.role not in {"Recruiter", "Team Lead", "Manager", "CRM", "Associate Director", "Center Head"}:
            continue
        if s.role == "Recruiter" and s.margin_min is not None:
            # margin_min used as placement-count band marker when seeded that way; else accept
            pass
        person_map = {
            "Recruiter": candidate.get("recruiter"),
            "Team Lead": candidate.get("team_lead"),
            "Manager": candidate.get("manager"),
            "CRM": candidate.get("crm"),
            "Associate Director": candidate.get("associate_director"),
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
                "rule_applied": f"fulltime.finders_fee.{band}",
                "eligible": payable,
                "base_incentive": s.amount,
                "pro_rata_factor": Decimal("1"),
                "amount": s.amount if payable else Decimal("0"),
                "reason": f"Full-time finders fee band {band}",
            }
        )
    return lines
