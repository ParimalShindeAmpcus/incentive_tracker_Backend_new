"""Hours service."""

from decimal import Decimal
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
    PublishedHoursOut,
    VersionMetaOut,
)
from app.repositories.candidates import candidate_repository
from app.repositories.entities.hours import HoursRow
from app.repositories.hours import hours_repository
from app.services.vlookup.normalization import normalize_month_year


def list_versions(db: Session, division: Optional[str] = None) -> List[VersionMetaOut]:
    rows = hours_repository.list_versions(db, division=division)
    return [VersionMetaOut.model_validate(r) for r in rows]


def get_published_for_month(db: Session, month: str) -> PublishedHoursOut:
    """
    Return hours_rows from the latest published hours_data_versions that contains
    rows for the given Incentive Month (YYYY-MM). Does not combine multiple versions.
    """
    month_key = normalize_month_year(month) or (month or "").strip()
    if not month_key or len(month_key) != 7:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month must be a valid YYYY-MM value (e.g. 2026-08)",
        )
    version_id = hours_repository.get_latest_version_id_for_month(db, month_key)
    if version_id is None:
        return PublishedHoursOut(month_key=month_key, version=None, rows=[])
    version = hours_repository.get_version(db, version_id)
    rows = hours_repository.list_rows_for_version_month(db, version_id, month_key)
    # Deduplicate by external candidate id + client (latest row id wins)
    by_key: dict[str, HoursRow] = {}
    for row in rows:
        ext = ""
        if row.candidate is not None:
            ext = (row.candidate.external_candidate_id or "").strip().lower()
        client = (row.client or "").strip().lower()
        key = f"{ext}::{client}" if client else ext
        existing = by_key.get(key)
        if existing is None or row.id >= existing.id:
            by_key[key] = row
    return PublishedHoursOut(
        month_key=month_key,
        version=VersionMetaOut.model_validate(version) if version else None,
        rows=[_row_out(r) for r in by_key.values()],
    )


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
    # Normalize month keys before persist so Hours & Benchmark can query by YYYY-MM.
    normalized_rows: List[HoursRowIn] = []
    for row in payload.rows:
        month_key = normalize_month_year(row.month_key or "") if row.month_key else None
        if row.month_key and not month_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid month_key for Candidate ID {row.external_candidate_id or row.candidate_id}: {row.month_key}",
            )
        data = row.model_dump()
        data["month_key"] = month_key
        normalized_rows.append(HoursRowIn(**data))

    # Validate all candidates first — fail closed (no partial publish).
    unknown: List[str] = []
    resolved_rows = []
    for row in normalized_rows:
        try:
            resolved_rows.append(_resolve_row_payload(db, row))
        except HTTPException as exc:
            if exc.status_code == status.HTTP_400_BAD_REQUEST:
                unknown.append(str(row.external_candidate_id or row.candidate_id or "?"))
            else:
                raise
    if unknown:
        uniq = sorted({u for u in unknown if u})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unknown Candidate ID(s) — upload candidates first before publishing hours: "
                + ", ".join(uniq[:25])
                + ("…" if len(uniq) > 25 else "")
            ),
        )

    try:
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
    except Exception:
        db.rollback()
        raise
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
