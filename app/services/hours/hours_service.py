"""Hours service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.hours.schemas import (
    CreateHoursVersionRequest,
    HoursBenchmarkOut,
    HoursBenchmarkUpdate,
    HoursRowOut,
    HoursVersionDetail,
    VersionMetaOut,
)
from app.repositories.hours import hours_repository


def list_versions(db: Session, division: Optional[str] = None) -> List[VersionMetaOut]:
    rows = hours_repository.list_versions(db, division=division)
    return [VersionMetaOut.model_validate(r) for r in rows]


def get_version_detail(db: Session, version_id: int) -> HoursVersionDetail:
    version = hours_repository.get_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return HoursVersionDetail(
        version=VersionMetaOut.model_validate(version),
        rows=[HoursRowOut.model_validate(r) for r in version.rows],
    )


def create_version(
    db: Session,
    payload: CreateHoursVersionRequest,
    uploaded_by: Optional[int] = None,
) -> HoursVersionDetail:
    version = hours_repository.create_version(
        db,
        version_label=payload.version_label,
        division=payload.division,
        source_filename=payload.source_filename,
        notes=payload.notes,
        uploaded_by=uploaded_by,
    )
    hours_repository.create_rows(db, version, [r.model_dump() for r in payload.rows])
    db.commit()
    return get_version_detail(db, version.id)


def list_benchmarks(db: Session) -> List[HoursBenchmarkOut]:
    rows = hours_repository.list_benchmarks(db)
    return [HoursBenchmarkOut.model_validate(r) for r in rows]


def update_benchmark(
    db: Session,
    division: str,
    payload: HoursBenchmarkUpdate,
    updated_by: Optional[int] = None,
) -> HoursBenchmarkOut:
    existing = hours_repository.get_benchmark(db, division)
    is_active = payload.is_active if payload.is_active is not None else (existing.is_active if existing else True)
    description = payload.description if payload.description is not None else (existing.description if existing else None)
    row = hours_repository.upsert_benchmark(
        db,
        division=division,
        benchmark_hours=payload.benchmark_hours,
        description=description,
        is_active=is_active,
        updated_by=updated_by,
    )
    db.commit()
    db.refresh(row)
    return HoursBenchmarkOut.model_validate(row)
