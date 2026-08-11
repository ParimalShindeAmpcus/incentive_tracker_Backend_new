from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import candidate_repo
from app.services import audit_service, duplicate_service
from app.utils.names import normalize_client, normalize_name
from app.utils.pagination import paginate


def create_or_update_candidate(db: Session, *, version_id: int, division: Optional[str], payload: dict):
    """Only place that creates/updates durable candidates master rows."""
    existing = candidate_repo.get_by_external_id(
        db, payload["external_candidate_id"], division=division
    )
    fields = {
        **payload,
        "normalized_name": payload.get("normalized_name")
        or normalize_name(payload.get("candidate_name")),
        "normalized_client": payload.get("normalized_client")
        or normalize_client(payload.get("client")),
        "division": division,
        "last_touched_version_id": version_id,
    }
    if existing:
        return candidate_repo.update_candidate(db, existing, **fields), "updated"
    fields["source_version_id"] = version_id
    return candidate_repo.create_candidate(db, **fields), "created"


def list_candidates(db: Session, *, division: Optional[str] = None, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    rows = candidate_repo.list_candidates(db, division=division, offset=offset, limit=page_size)
    total = candidate_repo.count_candidates(db, division=division)
    return paginate(rows, total, page, page_size)


def get_candidate(db: Session, candidate_id: int):
    row = candidate_repo.get_candidate(db, candidate_id)
    if not row:
        raise NotFoundError(f"Candidate {candidate_id} not found")
    return row


def ingest_rows(
    db: Session,
    *,
    user: User,
    version_label: str,
    filename: Optional[str],
    division: Optional[str],
    rows: list[dict],
    notes: Optional[str] = None,
):
    from app.services import candidate_data_service

    return candidate_data_service.create_version_from_rows(
        db,
        user=user,
        version_label=version_label,
        filename=filename,
        division=division,
        rows=rows,
        notes=notes,
    )
