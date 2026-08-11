"""Project-end repository — SQL only."""

from typing import List, Optional, Sequence

from sqlalchemy.orm import Session, joinedload

from app.repositories.entities.project_end import ProjectEndRecord, ProjectEndVersion


def list_versions(db: Session, division: Optional[str] = None) -> List[ProjectEndVersion]:
    q = db.query(ProjectEndVersion)
    if division:
        q = q.filter(ProjectEndVersion.division == division)
    return q.order_by(ProjectEndVersion.id.desc()).all()


def get_version(db: Session, version_id: int) -> Optional[ProjectEndVersion]:
    return (
        db.query(ProjectEndVersion)
        .options(joinedload(ProjectEndVersion.records))
        .filter(ProjectEndVersion.id == version_id)
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
) -> ProjectEndVersion:
    version = ProjectEndVersion(
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


def create_records(
    db: Session,
    version: ProjectEndVersion,
    rows: Sequence[dict],
) -> List[ProjectEndRecord]:
    created: List[ProjectEndRecord] = []
    for row in rows:
        item = ProjectEndRecord(
            version_id=version.id,
            candidate_id=row["candidate_id"],
            project_end_date=row.get("project_end_date"),
            project_end=row.get("project_end", True),
            project_end_source=row.get("project_end_source"),
            hours_before_project_end=row.get("hours_before_project_end"),
            eligibility_flag=row.get("eligibility_flag"),
            raw_candidate_name=row.get("raw_candidate_name"),
        )
        db.add(item)
        created.append(item)
    version.row_count = len(created)
    db.flush()
    return created
