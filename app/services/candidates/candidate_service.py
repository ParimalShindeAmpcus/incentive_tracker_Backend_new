from datetime import date
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
from app.repositories.entities.candidate import Candidate


def _to_candidate_out(row: Candidate) -> CandidateOut:
    dto = CandidateOut.model_validate(row)
    if row.end_date:
        dto.is_project_ended = row.end_date <= date.today()
    else:
        dto.is_project_ended = False
    return dto


def list_candidates(
    db: Session,
    *,
    division: Optional[str] = None,
    project_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> PaginatedCandidates:
    skip = max(page - 1, 0) * page_size
    rows, total = candidate_repository.list_candidates(
        db, division=division, project_status=project_status, skip=skip, limit=page_size
    )
    return PaginatedCandidates(
        items=[_to_candidate_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_candidate(db: Session, candidate_id: int) -> CandidateOut:
    row = candidate_repository.get_candidate(db, candidate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return _to_candidate_out(row)


def update_candidate(db: Session, candidate_id: int, payload: CandidateUpdate) -> CandidateOut:
    row = candidate_repository.get_candidate(db, candidate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    data = payload.model_dump(exclude_unset=True)
    if "candidate_name" in data and data["candidate_name"]:
        data["normalized_name"] = data["candidate_name"].strip().lower()
    if "client" in data and data["client"]:
        data["normalized_client"] = data["client"].strip().lower()

    # If end_date is set and has passed or is today, automatically inactivate/exclude candidate
    if "end_date" in data and data["end_date"]:
        end_val = data["end_date"]
        if isinstance(end_val, str):
            from datetime import datetime
            try:
                end_val = datetime.strptime(end_val, "%Y-%m-%d").date()
            except ValueError:
                end_val = None
        if end_val and end_val <= date.today():
            data["incentive_active"] = False
            if not data.get("status") or data.get("status") == "Active":
                data["status"] = "Inactive (Excluded)"
            data.setdefault("inactivation_reason", f"Project ended on {end_val}")

    try:
        updated = candidate_repository.update_candidate(db, row, data)
        db.commit()
        db.refresh(updated)
        return _to_candidate_out(updated)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update candidate record: {str(e)}",
        )


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
    try:
        version = candidate_repository.create_version(
            db,
            version_label=payload.version_label,
            division=payload.division,
            source_filename=payload.source_filename,
            notes=payload.notes,
            uploaded_by=uploaded_by,
            row_count=len(payload.rows),
        )
        row_dicts = [r.model_dump() for r in payload.rows]
        created = candidate_repository.create_candidates(db, version, row_dicts)
        version.row_count = len(created)
        db.commit()
        db.refresh(version)
        return CandidateVersionCreateResponse(
            version=CandidateVersionOut.model_validate(version),
            created_count=len(created),
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create candidate version: {str(e)}",
        )

