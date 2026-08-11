"""Recruiter master HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.recruiters.schemas import (
    CreateRecruiterVersionRequest,
    RecruiterStatusOut,
    RecruiterVersionCreateResponse,
    RecruiterVersionOut,
)
from app.services.common.deps import CurrentUser, DbSession
from app.services.recruiters import recruiter_service

router = APIRouter()


@router.get("/versions", response_model=List[RecruiterVersionOut])
def list_versions(db: DbSession, division: Optional[str] = Query(None)) -> List[RecruiterVersionOut]:
    return recruiter_service.list_versions(db, division=division)


@router.get("/versions/{version_id}", response_model=RecruiterVersionOut)
def get_version(version_id: int, db: DbSession) -> RecruiterVersionOut:
    return recruiter_service.get_version(db, version_id)


@router.get("/versions/{version_id}/statuses", response_model=List[RecruiterStatusOut])
def get_statuses(version_id: int, db: DbSession) -> List[RecruiterStatusOut]:
    return recruiter_service.get_version_statuses(db, version_id)


@router.post("/versions", response_model=RecruiterVersionCreateResponse)
def create_version(
    payload: CreateRecruiterVersionRequest,
    db: DbSession,
    user: CurrentUser,
) -> RecruiterVersionCreateResponse:
    return recruiter_service.create_version(db, payload, uploaded_by=user.id)
