"""Hours repository — SQL only."""

from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session, joinedload

from app.repositories.entities.hours import HoursBenchmark, HoursDataVersion, HoursRow


def list_versions(db: Session, division: Optional[str] = None) -> List[HoursDataVersion]:
    q = db.query(HoursDataVersion)
    if division:
        q = q.filter(HoursDataVersion.division == division)
    return q.order_by(HoursDataVersion.id.desc()).all()


def get_version(db: Session, version_id: int) -> Optional[HoursDataVersion]:
    return (
        db.query(HoursDataVersion)
        .options(joinedload(HoursDataVersion.rows).joinedload(HoursRow.candidate))
        .filter(HoursDataVersion.id == version_id)
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
) -> HoursDataVersion:
    version = HoursDataVersion(
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


def create_rows(db: Session, version: HoursDataVersion, rows: Sequence[dict]) -> List[HoursRow]:
    created: List[HoursRow] = []
    for row in rows:
        item = HoursRow(
            version_id=version.id,
            candidate_id=row["candidate_id"],
            hours_worked=row["hours_worked"],
            work_date=row.get("work_date"),
            month_key=row.get("month_key"),
            client=row.get("client"),
            source_row=row.get("source_row"),
            raw_candidate_name=row.get("raw_candidate_name"),
            match_method=row.get("match_method"),
            match_confidence=row.get("match_confidence"),
        )
        db.add(item)
        created.append(item)
    version.row_count = len(created)
    db.flush()
    return created


def list_benchmarks(db: Session) -> List[HoursBenchmark]:
    return db.query(HoursBenchmark).order_by(HoursBenchmark.division).all()


def get_benchmark(db: Session, division: str) -> Optional[HoursBenchmark]:
    return db.query(HoursBenchmark).filter(HoursBenchmark.division == division).first()


def upsert_benchmark(
    db: Session,
    *,
    division: str,
    benchmark_hours: Decimal,
    description: Optional[str] = None,
    is_active: bool = True,
    updated_by: Optional[int] = None,
) -> HoursBenchmark:
    row = get_benchmark(db, division)
    if row is None:
        row = HoursBenchmark(
            division=division,
            benchmark_hours=benchmark_hours,
            description=description,
            is_active=is_active,
            updated_by=updated_by,
        )
        db.add(row)
    else:
        row.benchmark_hours = benchmark_hours
        if description is not None:
            row.description = description
        row.is_active = is_active
        row.updated_by = updated_by
        db.add(row)
    db.flush()
    return row
