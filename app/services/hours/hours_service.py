"""Hours service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.hours.schemas import (
    CreateHoursVersionRequest,
    HoursBenchmarkOut,
    HoursBenchmarkUpdate,
    HoursRowHoursUpdate,
    HoursRowIn,
    HoursRowOut,
    HoursVersionDetail,
    VersionMetaOut,
)
from app.repositories.candidates import candidate_repository
from app.repositories.entities.hours import HoursRow
from app.repositories.hours import hours_repository
from decimal import Decimal


def list_versions(db: Session, division: Optional[str] = None) -> List[VersionMetaOut]:
    rows = hours_repository.list_versions(db, division=division)
    return [VersionMetaOut.model_validate(r) for r in rows]


def _row_out(row: HoursRow) -> HoursRowOut:
    cand = row.candidate
    return HoursRowOut(
        id=row.id,
        version_id=row.version_id,
        candidate_id=row.candidate_id,
        external_candidate_id=cand.external_candidate_id if cand else None,
        candidate_name=(cand.candidate_name if cand else None) or row.raw_candidate_name,
        work_date=row.work_date,
        month_key=row.month_key,
        hours_worked=row.hours_worked,
        client=row.client or (cand.client if cand else None),
        source_row=row.source_row,
        raw_candidate_name=row.raw_candidate_name,
        match_method=row.match_method,
        match_confidence=row.match_confidence,
        created_at=row.created_at,
    )


def get_version_detail(db: Session, version_id: int) -> HoursVersionDetail:
    version = hours_repository.get_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return HoursVersionDetail(
        version=VersionMetaOut.model_validate(version),
        rows=[_row_out(r) for r in version.rows],
    )


def _resolve_row_payload(db: Session, row: HoursRowIn) -> dict:
    match_method = "candidate_id"
    if row.candidate_id is not None:
        candidate = candidate_repository.get_candidate(db, row.candidate_id)
        if candidate is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown candidate_id: {row.candidate_id}",
            )
        resolved_id = candidate.id
    else:
        external = (row.external_candidate_id or "").strip()
        candidate = candidate_repository.get_candidate_by_external_id(db, external)
        if candidate is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown Candidate ID: {external}. Upload candidates first.",
            )
        resolved_id = candidate.id
        match_method = "external_candidate_id"

    return {
        "candidate_id": resolved_id,
        "hours_worked": row.hours_worked,
        "work_date": row.work_date,
        "month_key": row.month_key,
        "client": row.client or (candidate.client if candidate else None),
        "raw_candidate_name": row.raw_candidate_name or (candidate.candidate_name if candidate else None),
        "source_row": row.source_row,
        "match_method": match_method,
        "match_confidence": "exact",
    }


def create_version(
    db: Session,
    payload: CreateHoursVersionRequest,
    uploaded_by: Optional[int] = None,
) -> HoursVersionDetail:
    resolved_rows = [_resolve_row_payload(db, r) for r in payload.rows]
    version = hours_repository.create_version(
        db,
        version_label=payload.version_label,
        division=payload.division,
        source_filename=payload.source_filename,
        notes=payload.notes,
        uploaded_by=uploaded_by,
    )
    hours_repository.create_rows(db, version, resolved_rows)
    db.commit()
    return get_version_detail(db, version.id)


def update_row_hours(
    db: Session,
    row_id: int,
    payload: HoursRowHoursUpdate,
) -> HoursRowOut:
    row = hours_repository.get_row(db, row_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hours row not found")
    hours_worked = payload.hours_worked
    if hours_worked < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hours Worked must be greater than or equal to 0",
        )
    updated = hours_repository.update_row_hours(db, row, Decimal(hours_worked))
    db.commit()
    db.refresh(updated)
    # Reload with candidate for enriched out
    reloaded = hours_repository.get_row(db, updated.id)
    return _row_out(reloaded or updated)


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
