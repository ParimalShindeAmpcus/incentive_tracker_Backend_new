from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.hours import HoursBenchmark, HoursDataVersion, HoursRow


def create_version(db: Session, **kwargs) -> HoursDataVersion:
    row = HoursDataVersion(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_version(db: Session, version_id: int) -> Optional[HoursDataVersion]:
    return db.query(HoursDataVersion).filter(HoursDataVersion.id == version_id).first()


def list_versions(db: Session, *, offset: int = 0, limit: int = 50) -> List[HoursDataVersion]:
    return (
        db.query(HoursDataVersion)
        .order_by(HoursDataVersion.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_versions(db: Session) -> int:
    return db.query(HoursDataVersion).count()


def add_row(db: Session, **kwargs) -> HoursRow:
    row = HoursRow(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_rows(db: Session, version_id: int) -> List[HoursRow]:
    return db.query(HoursRow).filter(HoursRow.version_id == version_id).all()


def get_benchmark(db: Session, division: str) -> Optional[HoursBenchmark]:
    return (
        db.query(HoursBenchmark)
        .filter(HoursBenchmark.division == division, HoursBenchmark.is_active.is_(True))
        .first()
    )
