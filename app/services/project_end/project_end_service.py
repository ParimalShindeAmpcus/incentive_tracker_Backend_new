"""Project-end service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project_end.schemas import (
    CreateProjectEndVersionRequest,
    ProjectEndRecordOut,
    ProjectEndVersionDetail,
    ProjectEndVersionOut,
)
from app.repositories.project_end import project_end_repository


def list_versions(db: Session, division: Optional[str] = None) -> List[ProjectEndVersionOut]:
    rows = project_end_repository.list_versions(db, division=division)
    return [ProjectEndVersionOut.model_validate(r) for r in rows]


def get_version(db: Session, version_id: int) -> ProjectEndVersionDetail:
    version = project_end_repository.get_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return ProjectEndVersionDetail(
        version=ProjectEndVersionOut.model_validate(version),
        records=[ProjectEndRecordOut.model_validate(r) for r in version.records],
    )


def create_version(
    db: Session,
    payload: CreateProjectEndVersionRequest,
    uploaded_by: Optional[int] = None,
) -> ProjectEndVersionDetail:
    version = project_end_repository.create_version(
        db,
        version_label=payload.version_label,
        division=payload.division,
        source_filename=payload.source_filename,
        notes=payload.notes,
        uploaded_by=uploaded_by,
    )
    project_end_repository.create_records(db, version, [r.model_dump() for r in payload.records])
    db.commit()
    return get_version(db, version.id)
