"""Nashik strategy: margin recurring + team lead pro-rata + leadership one-time + project-end special.

Amounts and thresholds are loaded from incentive_slabs / hours_benchmarks.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.models.incentive_slab import IncentiveSlab
from app.services.calculation.rules import pro_rata


def calculate_nashik(
    *,
    candidate: Dict[str, Any],
    hours: Decimal,
    benchmark: Decimal,
    slabs: List[IncentiveSlab],
    project_ended_before_benchmark: bool,
    recruiter_payable: bool,
) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    margin = candidate.get("margin")
    margin = Decimal(str(margin)) if margin is not None else None

    if project_ended_before_benchmark:
        special = next((s for s in slabs if s.slab_type == "PROJECT_END_SPECIAL"), None)
        amount = special.amount if special else Decimal("2000")
        lines.append(
            {
                "role": "Recruiter",
                "person": candidate.get("recruiter") or "",
                "incentive_type": "SPECIAL",
                "rule_applied": "nashik.project_end_special",
                "eligible": recruiter_payable and bool(candidate.get("recruiter")),
                "base_incentive": amount,
                "pro_rata_factor": Decimal("1"),
                "amount": amount if recruiter_payable else Decimal("0"),
                "reason": "Project ended before benchmark hours",
            }
        )
        return lines

    # Low margin one-time
    if margin is not None and margin < Decimal("1"):
        low = next((s for s in slabs if s.slab_type == "LOW_MARGIN_ONETIME"), None)
        if low:
            lines.append(
                {
                    "role": "Recruiter",
                    "person": candidate.get("recruiter") or "",
                    "incentive_type": "ONETIME",
                    "rule_applied": "nashik.low_margin_onetime",
                    "eligible": recruiter_payable and bool(candidate.get("recruiter")),
                    "base_incentive": low.amount,
                    "pro_rata_factor": Decimal("1"),
                    "amount": low.amount if recruiter_payable else Decimal("0"),
                    "reason": "Low margin one-time",
                }
            )
    elif margin is not None:
        slab = next(
            (
                s
                for s in slabs
                if s.slab_type == "MARGIN_RECURRING"
                and s.role == "Recruiter"
                and (s.margin_min is None or margin >= s.margin_min)
                and (s.margin_max is None or margin <= s.margin_max)
            ),
            None,
        )
        if slab:
            amount, factor = pro_rata(slab.amount, hours, benchmark)
            lines.append(
                {
                    "role": "Recruiter",
                    "person": candidate.get("recruiter") or "",
                    "incentive_type": "RECURRING",
                    "rule_applied": "nashik.margin_recurring",
                    "eligible": recruiter_payable and bool(candidate.get("recruiter")),
                    "base_incentive": slab.amount,
                    "pro_rata_factor": factor,
                    "amount": amount if recruiter_payable else Decimal("0"),
                    "reason": "Margin recurring slab",
                }
            )

    tl_slab = next((s for s in slabs if s.slab_type == "TEAM_LEAD_RECURRING"), None)
    if tl_slab and candidate.get("team_lead"):
        amount, factor = pro_rata(tl_slab.amount, hours, benchmark)
        lines.append(
            {
                "role": "Team Lead",
                "person": candidate["team_lead"],
                "incentive_type": "RECURRING",
                "rule_applied": "nashik.team_lead",
                "eligible": True,
                "base_incentive": tl_slab.amount,
                "pro_rata_factor": factor,
                "amount": amount,
                "reason": "Team lead per placement",
            }
        )

    if hours >= benchmark:
        for s in slabs:
            if s.slab_type != "LEADERSHIP_ONETIME":
                continue
            person = _person_for_role(candidate, s.role)
            if not person:
                continue
            lines.append(
                {
                    "role": s.role,
                    "person": person,
                    "incentive_type": "ONETIME",
                    "rule_applied": "nashik.leadership_onetime",
                    "eligible": True,
                    "base_incentive": s.amount,
                    "pro_rata_factor": Decimal("1"),
                    "amount": s.amount,
                    "reason": "Leadership one-time after benchmark hours",
                }
            )
    return lines


def _person_for_role(candidate: Dict[str, Any], role: str) -> Optional[str]:
    mapping = {
        "Team Lead": "team_lead",
        "Manager": "manager",
        "Senior Manager": "senior_manager",
        "CRM": "crm",
        "Associate Director": "associate_director",
        "Center Head": "center_head",
        "AVP": "avp",
        "Recruiter": "recruiter",
    }
    key = mapping.get(role)
    return candidate.get(key) if key else None
