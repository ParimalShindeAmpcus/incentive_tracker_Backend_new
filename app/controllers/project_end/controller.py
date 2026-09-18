"""Project-end HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.models.project_end.schemas import (
    CreateProjectEndVersionRequest,
    ProjectEndVersionDetail,
    ProjectEndVersionOut,
)
from app.services.common.deps import CurrentUser, DbSession, get_current_user
from app.services.project_end import project_end_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/versions", response_model=List[ProjectEndVersionOut])
def list_versions(db: DbSession, user: CurrentUser, division: Optional[str] = Query(None)) -> List[ProjectEndVersionOut]:
    _ = user
    return project_end_service.list_versions(db, division=division)


@router.get("/versions/{version_id}", response_model=ProjectEndVersionDetail)
def get_version(version_id: int, db: DbSession, user: CurrentUser) -> ProjectEndVersionDetail:
    _ = user
    return project_end_service.get_version(db, version_id)


@router.post("/versions", response_model=ProjectEndVersionDetail)
def create_version(
    payload: CreateProjectEndVersionRequest,
    db: DbSession,
    user: CurrentUser,
) -> ProjectEndVersionDetail:
    return project_end_service.create_version(db, payload, uploaded_by=user.id)
