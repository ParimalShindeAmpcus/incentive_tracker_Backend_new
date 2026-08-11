from io import BytesIO
from typing import List, Optional

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.repositories import candidate_repo
from app.schemas.vlookup import VLookupMatchRequest, VLookupMatchResponse, VLookupMatchResult
from app.services.matching.candidate_matcher import MatchInput, match_row


TEMPLATE_COLUMNS = [
    "Candidate ID",
    "Candidate Name",
    "Client",
    "Hours",
]


def build_template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "VLookup Template"
    ws.append(TEMPLATE_COLUMNS)
    ws.append(["CAND-001", "Jane Doe", "Acme Corp", 160])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def match(db: Session, payload: VLookupMatchRequest) -> VLookupMatchResponse:
    candidates = candidate_repo.all_for_matching(db, division=payload.division)
    results: List[VLookupMatchResult] = []
    matched = unmatched = low = 0
    for row in payload.rows:
        outcome = match_row(
            MatchInput(
                candidate_id=row.candidate_id,
                candidate_name=row.candidate_name,
                client=row.client,
                source_row_ref=row.source_row_ref,
            ),
            candidates,
        )
        if outcome.match_result == "MATCHED":
            matched += 1
        elif outcome.match_result == "LOW_CONFIDENCE":
            low += 1
        else:
            unmatched += 1
        results.append(
            VLookupMatchResult(
                source_row_ref=row.source_row_ref,
                source_candidate_id=row.candidate_id,
                source_candidate_name=row.candidate_name,
                source_client=row.client,
                matched_candidate_id=outcome.candidate.id if outcome.candidate else None,
                matched_external_id=(
                    outcome.candidate.external_candidate_id if outcome.candidate else None
                ),
                matched_name=outcome.candidate.candidate_name if outcome.candidate else None,
                match_method=outcome.match_method,
                match_result=outcome.match_result,
                confidence=outcome.confidence,
            )
        )
    return VLookupMatchResponse(
        total=len(results),
        matched=matched,
        unmatched=unmatched,
        low_confidence=low,
        results=results,
    )
