"""Candidate service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.candidates.schemas import (
    CandidateOut,
    CandidateUpdate,
    CandidateVersionCreateResponse,
    CandidateVersionOut,
    CreateVersionRequest,
    PaginatedCandidates,
)
from app.repositories.candidates import candidate_repository


def list_candidates(
    db: Session,
    *,
    division: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> PaginatedCandidates:
    skip = max(page - 1, 0) * page_size
    rows, total = candidate_repository.list_candidates(
        db, division=division, skip=skip, limit=page_size
    )
    return PaginatedCandidates(
        items=[CandidateOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_candidate(db: Session, candidate_id: int) -> CandidateOut:
    row = candidate_repository.get_candidate(db, candidate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return CandidateOut.model_validate(row)


def update_candidate(db: Session, candidate_id: int, payload: CandidateUpdate) -> CandidateOut:
    row = candidate_repository.get_candidate(db, candidate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    data = payload.model_dump(exclude_unset=True)
    if "candidate_name" in data and data["candidate_name"]:
        data["normalized_name"] = data["candidate_name"].strip().lower()

    # A candidate who has been marked Left must retain that employment status
    # in the master table, not only in a client-side dataset version.
    requested_status = str(data.get("status") or "").strip().upper()
    if requested_status in {"LEFT", "MARKED LEFT"}:
        data["status"] = "LEFT"
        data["is_active"] = False
        data["incentive_active"] = False
        data.setdefault("inactivation_reason", "Marked Left")

    updated = candidate_repository.update_candidate(db, row, data)
    db.commit()
    db.refresh(updated)
    return CandidateOut.model_validate(updated)


def list_versions(db: Session, division: Optional[str] = None) -> List[CandidateVersionOut]:
    rows = candidate_repository.list_versions(db, division=division)
    return [CandidateVersionOut.model_validate(r) for r in rows]


def get_version(db: Session, version_id: int) -> CandidateVersionOut:
    row = candidate_repository.get_version(db, version_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return CandidateVersionOut.model_validate(row)


def create_version(
    db: Session,
    payload: CreateVersionRequest,
    uploaded_by: Optional[int] = None,
) -> CandidateVersionCreateResponse:
    version = candidate_repository.create_version(
        db,
        version_label=payload.version_label,
        division=payload.division,
        source_filename=payload.source_filename,
        notes=payload.notes,
        uploaded_by=uploaded_by,
        row_count=0,
    )
    row_dicts = [r.model_dump() for r in payload.rows]
    created = candidate_repository.create_candidates(db, version, row_dicts)
    db.commit()
    db.refresh(version)
    return CandidateVersionCreateResponse(
        version=CandidateVersionOut.model_validate(version),
        created_count=len(created),
    )
