"""
Division resolver — derives the incentive "division" to run for one candidate.

The business requirement is that Hours-upload rows must not be used to infer
division. Instead, we classify the *matched* Candidate Master record into the
cycle's division via org (and related attributes).

- Ampcus Tech Client: resolved from organisation field only. No recruiter
  location condition applies.
- Sambhaji Nagar / Nashik: recruiter work location is the primary signal.

Note: In this codebase the Candidate Master already carries a `division`
classification field. The resolver still treats organization/recruiter location
as primary inputs for auditability, and uses the Candidate Master division as
the authoritative fallback/normalization source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.cycles.engines.ampcus_client import is_ampcus_client_division
from app.services.cycles.engines.ampcus_inhouse import (
    is_ampcus_inhouse_candidate,
    is_ampcus_inhouse_division,
)
from app.services.cycles.engines.sambhaji_nagar import is_sambhaji_nagar_division
from app.services.incentives.nashik_rules import is_nashik_division, is_nashik_office


SUPPORTED_DIVISIONS = ("nashik", "sambhajiNagar", "ampcusTechClient", "ampcusTechInhouse")


def _norm_text(value: Optional[str]) -> str:
    return str(value or "").strip()


def _normalize_division_code(value: Optional[str]) -> Optional[str]:
    v = _norm_text(value).strip().lower().replace(" ", "").replace("-", "")
    if not v:
        return None
    # Keep these values aligned with existing engine dispatch codes.
    if is_nashik_division(v):
        return "nashik"
    if is_sambhaji_nagar_division(v):
        return "sambhajiNagar"
    if is_ampcus_client_division(v):
        return "ampcusTechClient"
    if is_ampcus_inhouse_division(v):
        return "ampcusTechInhouse"
    return None


@dataclass(frozen=True)
class ResolvedCandidateDivision:
    resolved_division: str
    # For audit/debug: we expose what we used to decide.
    master_division: Optional[str]
    organization: Optional[str]
    recruiter_work_location: Optional[str]


def resolve_candidate_division(
    *,
    organization: Optional[str],
    recruiter_work_location: Optional[str],
    contract_type: Optional[str] = None,
    master_division: Optional[str] = None,
) -> ResolvedCandidateDivision:
    """
    Return a resolved division code for the incentive engine.

    Inputs:
    - organization: Candidate Master -> Organization
    - recruiter_work_location: Candidate Master -> Recruiter Work Location
    - contract_type: Candidate Master -> Contract Type (used only for fallback heuristics)
    - master_division: Candidate Master -> stored division classification
    """

    normalized_master = _normalize_division_code(master_division)
    if normalized_master:
        return ResolvedCandidateDivision(
            resolved_division=normalized_master,
            master_division=_norm_text(master_division) or None,
            organization=organization,
            recruiter_work_location=recruiter_work_location,
        )

    # Ampcus Tech Client — match on organisation only, no recruiter location check.
    org_lower = _norm_text(organization).lower()
    org_compact = org_lower.replace(" ", "").replace("-", "")
    if is_ampcus_inhouse_candidate(
        organization=organization,
        contract_type=contract_type,
    ):
        return ResolvedCandidateDivision(
            resolved_division="ampcusTechInhouse",
            master_division=_norm_text(master_division) or None,
            organization=organization,
            recruiter_work_location=recruiter_work_location,
        )

    if "ampcusclient" in org_compact or "ampcus client" in org_lower or "ampcustech" in org_compact or "ampcus tech" in org_lower:

        return ResolvedCandidateDivision(
            resolved_division="ampcusTechClient",
            master_division=_norm_text(master_division) or None,
            organization=organization,
            recruiter_work_location=recruiter_work_location,
        )

    # Do NOT map bare FULLTIME → In-House (Nashik FTE and other FTEs must not auto-enter).

    # Fallback heuristics based on recruiter location.
    loc = _norm_text(recruiter_work_location).lower()
    if "sambhaji" in loc or "aurangabad" in loc:
        return ResolvedCandidateDivision(
            resolved_division="sambhajiNagar",
            master_division=_norm_text(master_division) or None,
            organization=organization,
            recruiter_work_location=recruiter_work_location,
        )

    if is_nashik_office(recruiter_work_location):
        return ResolvedCandidateDivision(
            resolved_division="nashik",
            master_division=_norm_text(master_division) or None,
            organization=organization,
            recruiter_work_location=recruiter_work_location,
        )

    # Default to Nashik to avoid "no engine" failures.
    return ResolvedCandidateDivision(
        resolved_division="nashik",
        master_division=_norm_text(master_division) or None,
        organization=organization,
        recruiter_work_location=recruiter_work_location,
    )

