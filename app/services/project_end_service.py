from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import candidate_repo, project_end_repo
from app.services import audit_service
from app.services.file_parser.hours_normalizer import read_tabular_upload
from app.services.file_parser.project_end_parser import parse_project_end_dataframe
from app.services.matching.candidate_matcher import MatchInput, match_row
from app.utils.pagination import paginate


def upload_file(
    db: Session,
    *,
    user: User,
    content: bytes,
    filename: str,
    division: Optional[str] = None,
    version_label: Optional[str] = None,
    notes: Optional[str] = None,
):
    """Project-end upload matches existing candidates only — never creates candidates."""
    df = read_tabular_upload(content, filename)
    parsed = parse_project_end_dataframe(df)
    candidates = candidate_repo.all_for_matching(db, division=division)
    version = project_end_repo.create_version(
        db,
        version_label=version_label or filename,
        source_filename=filename,
        division=division,
        row_count=0,
        uploaded_by=user.id,
        notes=notes,
    )
    matched = unmatched = 0
    for row in parsed:
        outcome = match_row(
            MatchInput(
                candidate_id=row.get("candidate_id"),
                candidate_name=row.get("candidate_name"),
            ),
            candidates,
        )
        if not outcome.candidate or outcome.match_result in {"UNMATCHED", "LOW_CONFIDENCE"}:
            unmatched += 1
            continue
        project_end_repo.add_record(
            db,
            version_id=version.id,
            candidate_id=outcome.candidate.id,
            project_end_date=row.get("project_end_date"),
            project_end=True,
            project_end_source=row.get("project_end_source"),
            raw_candidate_name=row.get("candidate_name"),
            match_method=outcome.match_method,
        )
        matched += 1
    version.row_count = matched
    if matched == 0 and parsed:
        raise ValidationAppError(
            "No project-end rows matched existing candidates",
            details={"unmatched": unmatched, "parsed": len(parsed)},
        )
    audit_service.write(
        db,
        action=AuditAction.UPLOAD,
        user_id=user.id,
        entity_type="project_end_version",
        entity_id=str(version.id),
        details=f"Project-end upload matched={matched} unmatched={unmatched}",
    )
    db.commit()
    db.refresh(version)
    return {"version": version, "matched_rows": matched, "unmatched_rows": unmatched}


def list_versions(db: Session, *, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    rows = project_end_repo.list_versions(db, offset=offset, limit=page_size)
    total = len(rows) if page == 1 and len(rows) < page_size else (
        offset + len(rows) if len(rows) == page_size else offset + len(rows)
    )
    # approximate total via recount
    from app.models.project_end import ProjectEndVersion

    total = db.query(ProjectEndVersion).count()
    return paginate(rows, total, page, page_size)


def get_version(db: Session, version_id: int):
    row = project_end_repo.get_version(db, version_id)
    if not row:
        raise NotFoundError(f"Project-end version {version_id} not found")
    return row
