from datetime import date
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.candidates.schemas import (
    CandidateDuplicateInfo,
    CandidateOut,
    CandidateUpdate,
    CandidateVersionCreateResponse,
    CandidateVersionOut,
    CreateVersionRequest,
    PaginatedCandidates,
)
from app.repositories.candidates import candidate_repository
from app.repositories.entities.candidate import Candidate
from app.repositories.entities.user import User
from app.services.audit import audit_service


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


def update_candidate(db: Session, candidate_id: int, payload: CandidateUpdate, user: Optional[User] = None) -> CandidateOut:
    row = candidate_repository.get_candidate(db, candidate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    data = payload.model_dump(exclude_unset=True)
    if "candidate_name" in data and data["candidate_name"]:
        data["normalized_name"] = data["candidate_name"].strip().lower()
    if "client" in data and data["client"]:
        data["normalized_client"] = data["client"].strip().lower()

    try:
        updated = candidate_repository.update_candidate(db, row, data)
        audit_service.record_event(
            db,
            action="CANDIDATE_UPDATE",
            title=f"Updated candidate: {updated.candidate_name}",
            details=f"Updated candidate ID {updated.id} ({updated.start_id or 'No Start ID'})",
            user=user,
            metadata={"candidate_id": updated.id, "changes": list(data.keys())},
        )
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
    user: Optional[User] = None,
) -> CandidateVersionCreateResponse:
    try:
        version = candidate_repository.create_version(
            db,
            version_label=payload.version_label,
            division=payload.division,
            source_filename=payload.source_filename,
            notes=payload.notes,
            uploaded_by=user.id if user else None,
            row_count=len(payload.rows),
        )
        row_dicts = [r.model_dump(exclude_unset=True) for r in payload.rows]
        new_candidates, updated_candidates, duplicate_candidates, rejected_rows = candidate_repository.create_candidates(db, version, row_dicts)
        version.row_count = len(new_candidates) + len(updated_candidates) + len(duplicate_candidates)
        
        audit_service.record_event(
            db,
            action="FILE_UPLOAD",
            title=f"Uploaded Candidate Master: {payload.version_label}",
            details=f"File: {payload.source_filename} | Created: {len(new_candidates)}, Updated: {len(updated_candidates)}, Duplicates: {len(duplicate_candidates)}, Rejected: {len(rejected_rows)}",
            user=user,
            metadata={"version_id": version.id, "division": payload.division},
        )
        db.commit()
        db.refresh(version)

        duplicates: List[CandidateDuplicateInfo] = []
        for c, changed in updated_candidates:
            duplicates.append(
                CandidateDuplicateInfo(
                    identifier=f"{c.candidate_name} ({c.start_id or c.activity_id or c.external_candidate_id or 'ID'})",
                    status="UPDATED",
                    reason=f"Existing candidate matched by ID — updated {len(changed)} field(s): {', '.join(changed)}",
                    candidate_id=c.id,
                    activity_id=c.activity_id,
                    start_id=c.start_id,
                    changed_fields=changed,
                )
            )
        for c in duplicate_candidates:
            duplicates.append(
                CandidateDuplicateInfo(
                    identifier=f"{c.candidate_name} ({c.start_id or c.activity_id or c.external_candidate_id or 'ID'})",
                    status="DUPLICATE",
                    reason="Candidate already exists with identical supplied data — no changes made",
                    candidate_id=c.id,
                    activity_id=c.activity_id,
                    start_id=c.start_id,
                )
            )

        return CandidateVersionCreateResponse(
            version=CandidateVersionOut.model_validate(version),
            created_count=len(new_candidates),
            updated_count=len(updated_candidates),
            duplicate_count=len(duplicate_candidates),
            duplicates=duplicates,
            rejected_count=len(rejected_rows),
            rejected_rows=rejected_rows,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create candidate version: {str(e)}",
        )

