from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.candidate import CandidateOut, CandidateVersionCreateResponse, CandidateVersionOut
from app.services import candidate_data_service, candidate_service

router = APIRouter(tags=["candidate-data"])


@router.post("/candidate-data/versions", response_model=CandidateVersionCreateResponse)
async def upload_candidate_version(
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
    file: UploadFile = File(...),
    division: Optional[str] = Form(None),
    version_label: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
):
    content = await file.read()
    result = candidate_data_service.upload_file(
        db,
        user=user,
        content=content,
        filename=file.filename or "candidates.xlsx",
        division=division,
        version_label=version_label,
        notes=notes,
    )
    version = result["version"]
    return CandidateVersionCreateResponse(
        version=CandidateVersionOut(
            id=version.id,
            version_label=version.version_label,
            source_filename=version.source_filename,
            division=version.division,
            row_count=version.row_count,
            uploaded_by=version.uploaded_by,
            notes=version.notes,
            created_at=version.created_at,
            created_candidates=result["created_candidates"],
            updated_candidates=result["updated_candidates"],
        ),
        created_candidates=result["created_candidates"],
        updated_candidates=result["updated_candidates"],
        duplicates_flagged=result["duplicates_flagged"],
    )


@router.get("/candidate-data/versions")
def list_candidate_versions(
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    return candidate_data_service.list_versions(db, page=page, page_size=page_size)


@router.get("/candidate-data/versions/{version_id}", response_model=CandidateVersionOut)
def get_candidate_version(
    version_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    return candidate_data_service.get_version(db, version_id)


@router.get("/candidates")
def list_candidates(
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
    division: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    return candidate_service.list_candidates(db, division=division, page=page, page_size=page_size)


@router.get("/candidates/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    return candidate_service.get_candidate(db, candidate_id)
