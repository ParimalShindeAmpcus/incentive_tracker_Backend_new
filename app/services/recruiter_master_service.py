from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import recruiter_repo
from app.services import audit_service
from app.services.file_parser.hours_normalizer import read_tabular_upload
from app.services.file_parser.recruiter_parser import parse_recruiter_dataframe
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
    df = read_tabular_upload(content, filename)
    parsed = parse_recruiter_dataframe(df)
    version = recruiter_repo.create_version(
        db,
        version_label=version_label or filename,
        source_filename=filename,
        division=division,
        row_count=len(parsed),
        uploaded_by=user.id,
        notes=notes,
    )
    active = left = notice = 0
    for row in parsed:
        emp = recruiter_repo.find_employee_by_name(db, row["normalized_name"])
        if not emp:
            emp = recruiter_repo.create_employee(
                db,
                full_name=row["recruiter_name"],
                normalized_name=row["normalized_name"],
                role_title="Recruiter",
            )
        status = recruiter_repo.add_status(
            db,
            version_id=version.id,
            employee_id=emp.id,
            recruiter_name=row["recruiter_name"],
            normalized_name=row["normalized_name"],
            status=row["status"],
            effective_month=row.get("effective_month"),
        )
        val = status.status.value if hasattr(status.status, "value") else str(status.status)
        if val == "ACTIVE":
            active += 1
        elif val == "LEFT":
            left += 1
        else:
            notice += 1
    audit_service.write(
        db,
        action=AuditAction.UPLOAD,
        user_id=user.id,
        entity_type="recruiter_master_version",
        entity_id=str(version.id),
        details=f"Recruiter status upload rows={len(parsed)}",
    )
    db.commit()
    db.refresh(version)
    return {
        "version": version,
        "active_count": active,
        "left_count": left,
        "notice_count": notice,
    }


def list_versions(db: Session, *, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    rows = recruiter_repo.list_versions(db, offset=offset, limit=page_size)
    from app.models.recruiter import RecruiterMasterVersion

    total = db.query(RecruiterMasterVersion).count()
    return paginate(rows, total, page, page_size)


def get_version(db: Session, version_id: int):
    row = recruiter_repo.get_version(db, version_id)
    if not row:
        raise NotFoundError(f"Recruiter version {version_id} not found")
    return row
