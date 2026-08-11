"""Recruiter service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.recruiters.schemas import (
    CreateRecruiterVersionRequest,
    RecruiterStatusOut,
    RecruiterVersionCreateResponse,
    RecruiterVersionOut,
)
from app.repositories.recruiters import recruiter_repository


def list_versions(db: Session, division: Optional[str] = None) -> List[RecruiterVersionOut]:
    rows = recruiter_repository.list_versions(db, division=division)
    return [RecruiterVersionOut.model_validate(r) for r in rows]


def get_version(db: Session, version_id: int) -> RecruiterVersionOut:
    row = recruiter_repository.get_version(db, version_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return RecruiterVersionOut.model_validate(row)


def get_version_statuses(db: Session, version_id: int) -> List[RecruiterStatusOut]:
    version = recruiter_repository.get_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    rows = recruiter_repository.list_statuses(db, version_id)
    return [RecruiterStatusOut.model_validate(r) for r in rows]


def create_version(
    db: Session,
    payload: CreateRecruiterVersionRequest,
    uploaded_by: Optional[int] = None,
) -> RecruiterVersionCreateResponse:
    version = recruiter_repository.create_version(
        db,
        version_label=payload.version_label,
        division=payload.division,
        source_filename=payload.source_filename,
        notes=payload.notes,
        uploaded_by=uploaded_by,
    )
    created = recruiter_repository.create_statuses(
        db, version, [s.model_dump() for s in payload.statuses]
    )
    db.commit()
    db.refresh(version)
    return RecruiterVersionCreateResponse(
        version=RecruiterVersionOut.model_validate(version),
        created_count=len(created),
    )
