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


def get_latest_version_id_for_month(db: Session, month_key: str) -> Optional[int]:
    """Newest hours_data_versions.id that has at least one hours_rows row for month_key."""
    row = (
        db.query(HoursDataVersion.id)
        .join(HoursRow, HoursRow.version_id == HoursDataVersion.id)
        .filter(HoursRow.month_key == month_key)
        .order_by(HoursDataVersion.id.desc())
        .first()
    )
    return int(row[0]) if row else None


def list_rows_for_version_month(
    db: Session, version_id: int, month_key: str
) -> List[HoursRow]:
    return (
        db.query(HoursRow)
        .options(joinedload(HoursRow.candidate))
        .filter(HoursRow.version_id == version_id, HoursRow.month_key == month_key)
        .order_by(HoursRow.id.asc())
        .all()
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


def get_row(db: Session, row_id: int) -> Optional[HoursRow]:
    return (
        db.query(HoursRow)
        .options(joinedload(HoursRow.candidate))
        .filter(HoursRow.id == row_id)
        .first()
    )


def update_row_hours(db: Session, row: HoursRow, hours_worked: Decimal) -> HoursRow:
    row.hours_worked = hours_worked
    db.add(row)
    db.flush()
    return row


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
