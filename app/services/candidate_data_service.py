from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import candidate_repo
from app.services import audit_service, candidate_service, duplicate_service
from app.services.file_parser.hours_normalizer import read_tabular_upload
from app.services.file_parser.mis_parser import parse_mis_dataframe
from app.utils.pagination import paginate


def create_version_from_rows(
    db: Session,
    *,
    user: User,
    version_label: str,
    filename: Optional[str],
    division: Optional[str],
    rows: list[dict],
    notes: Optional[str] = None,
):
    version = candidate_repo.create_version(
        db,
        version_label=version_label,
        source_filename=filename,
        division=division,
        row_count=len(rows),
        uploaded_by=user.id,
        notes=notes,
    )
    dup_ids = duplicate_service.find_duplicate_external_ids(rows)
    created = updated = 0
    for row in rows:
        _, action = candidate_service.create_or_update_candidate(
            db, version_id=version.id, division=division, payload=row
        )
        if action == "created":
            created += 1
        else:
            updated += 1
    audit_service.write(
        db,
        action=AuditAction.UPLOAD,
        user_id=user.id,
        entity_type="candidate_data_version",
        entity_id=str(version.id),
        details=f"Uploaded {len(rows)} candidate rows from {filename}",
    )
    audit_service.write(
        db,
        action=AuditAction.IMPORT,
        user_id=user.id,
        entity_type="candidate_data_version",
        entity_id=str(version.id),
        details=f"Imported candidates created={created} updated={updated}",
    )
    db.commit()
    db.refresh(version)
    return {
        "version": version,
        "created_candidates": created,
        "updated_candidates": updated,
        "duplicates_flagged": len(dup_ids),
    }


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
    df = read_tabular_upload(content, filename)
    rows = parse_mis_dataframe(df)
    return create_version_from_rows(
        db,
        user=user,
        version_label=version_label or filename,
        filename=filename,
        division=division,
        rows=rows,
        notes=notes,
    )


def list_versions(db: Session, *, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    rows = candidate_repo.list_versions(db, offset=offset, limit=page_size)
    total = candidate_repo.count_versions(db)
    return paginate(rows, total, page, page_size)


def get_version(db: Session, version_id: int):
    row = candidate_repo.get_version(db, version_id)
    if not row:
        raise NotFoundError(f"Candidate version {version_id} not found")
    return row
