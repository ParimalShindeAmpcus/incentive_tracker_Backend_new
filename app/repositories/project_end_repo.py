from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.project_end import ProjectEndRecord, ProjectEndVersion


def create_version(db: Session, **kwargs) -> ProjectEndVersion:
    row = ProjectEndVersion(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_version(db: Session, version_id: int) -> Optional[ProjectEndVersion]:
    return db.query(ProjectEndVersion).filter(ProjectEndVersion.id == version_id).first()


def list_versions(db: Session, *, offset: int = 0, limit: int = 50) -> List[ProjectEndVersion]:
    return (
        db.query(ProjectEndVersion)
        .order_by(ProjectEndVersion.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def add_record(db: Session, **kwargs) -> ProjectEndRecord:
    row = ProjectEndRecord(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_records(db: Session, version_id: int) -> List[ProjectEndRecord]:
    return db.query(ProjectEndRecord).filter(ProjectEndRecord.version_id == version_id).all()
