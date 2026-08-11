from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import candidate_repo, hours_repo
from app.services import audit_service
from app.services.file_parser.hours_normalizer import normalize_hours_dataframe, read_tabular_upload
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
    """Hours upload → normalize → match → store. Never creates candidates."""
    df = read_tabular_upload(content, filename)
    normalized = normalize_hours_dataframe(df)
    candidates = candidate_repo.all_for_matching(db, division=division)
    version = hours_repo.create_version(
        db,
        version_label=version_label or filename,
        source_filename=filename,
        division=division,
        row_count=0,
        uploaded_by=user.id,
        notes=notes,
    )
    matched = unmatched = 0
    for row in normalized:
        outcome = match_row(
            MatchInput(
                candidate_id=row.get("candidate_id"),
                candidate_name=row.get("candidate_name"),
                client=row.get("client"),
                source_row_ref=str(row.get("source_row")),
            ),
            candidates,
        )
        if not outcome.candidate or outcome.match_result in {"UNMATCHED", "LOW_CONFIDENCE"}:
            unmatched += 1
            continue
        if outcome.match_result == "LOW_CONFIDENCE":
            # Never auto-accept fuzzy for storage into hours_rows (requires candidate_id FK)
            unmatched += 1
            continue
        hours_repo.add_row(
            db,
            version_id=version.id,
            candidate_id=outcome.candidate.id,
            work_date=row.get("work_date"),
            month_key=row.get("month_key"),
            hours_worked=row.get("hours_worked"),
            client=row.get("client"),
            source_row=row.get("source_row"),
            raw_candidate_name=row.get("candidate_name"),
            match_method=outcome.match_method,
            match_confidence=outcome.confidence,
        )
        matched += 1
    version.row_count = matched
    if matched == 0 and normalized:
        raise ValidationAppError(
            "No hours rows could be matched to existing candidates",
            details={"unmatched": unmatched, "parsed": len(normalized)},
        )
    audit_service.write(
        db,
        action=AuditAction.UPLOAD,
        user_id=user.id,
        entity_type="hours_data_version",
        entity_id=str(version.id),
        details=f"Hours upload matched={matched} unmatched={unmatched}",
    )
    db.commit()
    db.refresh(version)
    return {"version": version, "matched_rows": matched, "unmatched_rows": unmatched}


def list_versions(db: Session, *, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    rows = hours_repo.list_versions(db, offset=offset, limit=page_size)
    total = hours_repo.count_versions(db)
    return paginate(rows, total, page, page_size)


def get_version(db: Session, version_id: int):
    row = hours_repo.get_version(db, version_id)
    if not row:
        raise NotFoundError(f"Hours version {version_id} not found")
    return row
