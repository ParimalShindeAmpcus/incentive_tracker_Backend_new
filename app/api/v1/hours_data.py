from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.hours import HoursVersionDetail
from app.services import hours_service

router = APIRouter(prefix="/hours-data", tags=["hours-data"])


@router.post("/versions")
async def upload_hours_version(
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
    file: UploadFile = File(...),
    division: Optional[str] = Form(None),
    version_label: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
):
    content = await file.read()
    return hours_service.upload_file(
        db,
        user=user,
        content=content,
        filename=file.filename or "hours.xlsx",
        division=division,
        version_label=version_label,
        notes=notes,
    )


@router.get("/versions")
def list_versions(
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    return hours_service.list_versions(db, page=page, page_size=page_size)


@router.get("/versions/{version_id}", response_model=HoursVersionDetail)
def get_version(
    version_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    return hours_service.get_version(db, version_id)
