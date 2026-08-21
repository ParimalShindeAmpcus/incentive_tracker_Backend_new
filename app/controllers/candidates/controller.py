"""Candidate HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.candidates.schemas import (
    CandidateOut,
    CandidateUpdate,
    CandidateVersionCreateResponse,
    CandidateVersionOut,
    CreateVersionRequest,
    PaginatedCandidates,
)
from app.services.candidates import candidate_service
from app.services.common.deps import CurrentUser, DbSession

router = APIRouter()



@router.get("/candidates", response_model=PaginatedCandidates)
def list_candidates(
    db: DbSession,
    division: Optional[str] = Query(None),
    project_status: Optional[str] = Query(None, description="Filter by ACTIVE or ENDED project status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> PaginatedCandidates:
    return candidate_service.list_candidates(
        db, division=division, project_status=project_status, page=page, page_size=page_size
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateOut)
def get_candidate(candidate_id: int, db: DbSession) -> CandidateOut:
    return candidate_service.get_candidate(db, candidate_id)


@router.patch("/candidates/{candidate_id}", response_model=CandidateOut)
def patch_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    db: DbSession,
    user: CurrentUser,
) -> CandidateOut:
    return candidate_service.update_candidate(db, candidate_id, payload, user=user)


@router.get("/candidate-data/versions", response_model=List[CandidateVersionOut])
def list_versions(db: DbSession, division: Optional[str] = Query(None)) -> List[CandidateVersionOut]:
    return candidate_service.list_versions(db, division=division)


@router.get("/candidate-data/versions/{version_id}", response_model=CandidateVersionOut)
def get_version(version_id: int, db: DbSession) -> CandidateVersionOut:
    return candidate_service.get_version(db, version_id)


@router.post("/candidate-data/versions", response_model=CandidateVersionCreateResponse)
def create_version(
    payload: CreateVersionRequest,
    db: DbSession,
    user: CurrentUser,
) -> CandidateVersionCreateResponse:
    return candidate_service.create_version(db, payload, uploaded_by=user.id, user=user)

