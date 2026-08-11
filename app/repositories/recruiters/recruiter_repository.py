"""Recruiter repository — SQL only."""

from typing import List, Optional, Sequence

from sqlalchemy.orm import Session, joinedload

from app.repositories.entities.recruiter import (
    RecruiterMasterVersion,
    RecruiterStatus,
    RecruiterStatusEnum,
)


def list_versions(db: Session, division: Optional[str] = None) -> List[RecruiterMasterVersion]:
    q = db.query(RecruiterMasterVersion)
    if division:
        q = q.filter(RecruiterMasterVersion.division == division)
    return q.order_by(RecruiterMasterVersion.id.desc()).all()


def get_version(db: Session, version_id: int) -> Optional[RecruiterMasterVersion]:
    return (
        db.query(RecruiterMasterVersion)
        .options(joinedload(RecruiterMasterVersion.statuses))
        .filter(RecruiterMasterVersion.id == version_id)
        .first()
    )


def create_version(
    db: Session,
    *,
    version_label: str,
    division: Optional[str] = None,
    source_filename: Optional[str] = None,
    notes: Optional[str] = None,
    uploaded_by: Optional[int] = None,
) -> RecruiterMasterVersion:
    version = RecruiterMasterVersion(
        version_label=version_label,
        division=division,
        source_filename=source_filename,
        notes=notes,
        uploaded_by=uploaded_by,
        row_count=0,
    )
    db.add(version)
    db.flush()
    return version


def create_statuses(
    db: Session,
    version: RecruiterMasterVersion,
    rows: Sequence[dict],
) -> List[RecruiterStatus]:
    created: List[RecruiterStatus] = []
    for row in rows:
        name = row["recruiter_name"]
        status_raw = (row.get("status") or "ACTIVE").upper()
        try:
            status = RecruiterStatusEnum(status_raw)
        except ValueError:
            status = RecruiterStatusEnum.ACTIVE
        item = RecruiterStatus(
            version_id=version.id,
            employee_id=row.get("employee_id"),
            recruiter_name=name,
            normalized_name=name.strip().lower(),
            email=row.get("email"),
            organization=row.get("organization"),
            role=row.get("role"),
            status=status,
            effective_month=row.get("effective_month"),
            incentive_active=row.get("incentive_active", True),
            notes=row.get("notes"),
        )
        db.add(item)
        created.append(item)
    version.row_count = len(created)
    db.flush()
    return created


def list_statuses(db: Session, version_id: int) -> List[RecruiterStatus]:
    return (
        db.query(RecruiterStatus)
        .filter(RecruiterStatus.version_id == version_id)
        .order_by(RecruiterStatus.id)
        .all()
    )
