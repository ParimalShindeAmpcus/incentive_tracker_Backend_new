"""Resolve which Candidate Master rows belong to an incentive cycle."""

from __future__ import annotations

import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.repositories.candidates import candidate_repository
from app.repositories.cycles import cycle_repository
from app.repositories.entities.candidate import Candidate
from app.services.cycles.engines.ampcus_client import is_ampcus_client_division
from app.services.cycles.engines.ampcus_inhouse import is_ampcus_inhouse_division
from app.services.cycles.engines.sambhaji_nagar import is_sambhaji_nagar_division
from app.services.incentives.nashik_rules import is_nashik_division

_DEMO_EXTERNAL_ID = re.compile(
    r"^(TMP|BULK-(NASHIK|SAMBHAJINAGAR|AMPCUSTECHCLIENT|AMPCUSTECHINHOUSE))-\d+$",
    re.IGNORECASE,
)


def _norm_division(value: Optional[str]) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )


def is_seed_candidate(candidate: Candidate) -> bool:
    """Demo / seed rows that should not drive production cycles."""
    name = (candidate.candidate_name or "").strip().lower()
    if name.startswith("sample cand"):
        return True
    if name in {"fulltime hire", "demo recruiter"}:
        return True
    ext = (candidate.external_candidate_id or "").strip().upper()
    if _DEMO_EXTERNAL_ID.match(ext):
        return True
    return False


def candidate_matches_division(candidate: Candidate, cycle_division: str) -> bool:
    if (candidate.division or "").strip() == (cycle_division or "").strip():
        return True

    org = f"{candidate.organization or ''} {candidate.candidate_source or ''}".lower()
    contract = (candidate.contract_type or "").upper()

    if is_ampcus_client_division(cycle_division):
        return "ampcus tech" in org and "inhouse" not in org and contract != "INHOUSE"

    if is_ampcus_inhouse_division(cycle_division):
        return "inhouse" in org or contract == "INHOUSE"

    if is_sambhaji_nagar_division(cycle_division):
        loc = (candidate.recruiter_location or "").lower()
        return "sambhaji" in loc or "sambhajinagar" in loc or "sambhaji nagar" in loc

    if is_nashik_division(cycle_division):
        from app.services.incentives.nashik_rules import matches_nashik_company

        return matches_nashik_company(candidate.candidate_source, candidate.organization)


    # Other divisions: match explicit division tag only.
    return False


def resolve_candidates_for_cycle(db: Session, cycle) -> List[Candidate]:
    """
    Candidates in scope for this cycle.

    Prefer rows linked through cycle_payment_statuses so calculation never
    scans the entire master list (including seed/demo data).
    """
    payment_rows = cycle_repository.list_payment_statuses(db, cycle.id)
    if payment_rows:
        out: List[Candidate] = []
        for row in payment_rows:
            cand = candidate_repository.get_candidate(db, row.candidate_id)
            if cand is not None and not is_seed_candidate(cand):
                out.append(cand)
        return out

    if cycle.candidate_version_id:
        masters = candidate_repository.list_candidates_for_cycle(
            db, version_id=cycle.candidate_version_id
        )
        return [c for c in masters if not is_seed_candidate(c)]

    masters = candidate_repository.list_candidates_for_cycle(db, division=cycle.division)
    if masters:
        return [c for c in masters if not is_seed_candidate(c)]

    all_candidates = candidate_repository.list_all_candidates(db)
    return [
        c
        for c in all_candidates
        if candidate_matches_division(c, cycle.division) and not is_seed_candidate(c)
    ]


def candidate_ids_for_new_cycle(db: Session, division: str) -> List[int]:
    """Placement IDs to attach when a payment-gated cycle is created."""
    masters = candidate_repository.list_all_candidates(db)
    matched = [
        c.id
        for c in masters
        if candidate_matches_division(c, division) and not is_seed_candidate(c)
    ]
    return matched
