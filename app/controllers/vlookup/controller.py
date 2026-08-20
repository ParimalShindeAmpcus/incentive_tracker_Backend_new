"""VLOOKUP hours reconciliation HTTP routes."""

from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.models.vlookup.schemas import (
    VLookupActionResponse,
    VLookupHoursTemplateListResponse,
    VLookupMatchesByStatusResponse,
    VLookupMessyFileListResponse,
    VLookupPublishHoursResponse,
    VLookupRematchBody,
    VLookupReviewBody,
    VLookupStatsResponse,
    VLookupTemplateResponse,
    VLookupTemplateSearchResponse,
    VLookupUploadResponse,
)
from app.services.common.deps import CurrentUser, DbSession
from app.services.vlookup import vlookup_service

router = APIRouter()


@router.get("/template", response_model=VLookupTemplateResponse)
def template() -> VLookupTemplateResponse:
    return vlookup_service.template_info()


@router.post("/upload", response_model=VLookupUploadResponse)
def upload(
    db: DbSession,
    user: CurrentUser,
    template_file: UploadFile = File(..., description="Hours Template CSV/XLSX"),
    messy_file: UploadFile = File(..., description="Client hours CSV/XLSX"),
    target_month: Optional[str] = Form(None),
) -> VLookupUploadResponse:
    return vlookup_service.upload_template_and_messy(
        db,
        template_file=template_file,
        messy_file=messy_file,
        target_month=target_month,
        uploaded_by=getattr(user, "email", None) or str(user.id),
    )


@router.get("/stats", response_model=VLookupStatsResponse)
def stats(
    db: DbSession,
    user: CurrentUser,
    batch_id: Optional[str] = Query(None),
    month: Optional[str] = Query(None, description="YYYY-MM month to count results for"),
) -> VLookupStatsResponse:
    _ = user
    return vlookup_service.get_stats(db, batch_id=batch_id, month=month)


@router.get("/matches/{status}", response_model=VLookupMatchesByStatusResponse)
def matches_by_status(
    status: str,
    db: DbSession,
    user: CurrentUser,
    batch_id: Optional[str] = Query(None),
    month: Optional[str] = Query(None, description="YYYY-MM month to list results for"),
) -> VLookupMatchesByStatusResponse:
    _ = user
    return vlookup_service.get_matches_by_status(
        db, status=status, batch_id=batch_id, month=month
    )


@router.get("/template-candidates", response_model=VLookupTemplateSearchResponse)
def template_candidates(
    db: DbSession,
    user: CurrentUser,
    q: Optional[str] = Query(None),
    client: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
) -> VLookupTemplateSearchResponse:
    _ = user
    return vlookup_service.search_template_candidates(
        db, q=q, client=client, batch_id=batch_id, limit=limit
    )


@router.get("/hours-template", response_model=VLookupHoursTemplateListResponse)
def hours_template(
    db: DbSession,
    user: CurrentUser,
    batch_id: Optional[str] = Query(None),
) -> VLookupHoursTemplateListResponse:
    _ = user
    payload = vlookup_service.list_hours_template(db, batch_id=batch_id)
    return VLookupHoursTemplateListResponse(**payload)


@router.get("/messy-file", response_model=VLookupMessyFileListResponse)
def messy_file(
    db: DbSession,
    user: CurrentUser,
    batch_id: Optional[str] = Query(None),
) -> VLookupMessyFileListResponse:
    _ = user
    payload = vlookup_service.list_messy_file(db, batch_id=batch_id)
    return VLookupMessyFileListResponse(**payload)


@router.post("/matches/{match_id}/accept", response_model=VLookupActionResponse)
def accept_match(
    match_id: int,
    db: DbSession,
    user: CurrentUser,
    body: Optional[VLookupReviewBody] = None,
) -> VLookupActionResponse:
    payload = body or VLookupReviewBody()
    if not payload.reviewed_by:
        payload.reviewed_by = getattr(user, "email", None) or str(user.id)
    return vlookup_service.accept_match(db, match_id, payload)


@router.post("/matches/{match_id}/reject", response_model=VLookupActionResponse)
def reject_match(
    match_id: int,
    db: DbSession,
    user: CurrentUser,
    body: Optional[VLookupReviewBody] = None,
) -> VLookupActionResponse:
    payload = body or VLookupReviewBody()
    if not payload.reviewed_by:
        payload.reviewed_by = getattr(user, "email", None) or str(user.id)
    return vlookup_service.reject_match(db, match_id, payload)


@router.post("/matches/{match_id}/restore", response_model=VLookupActionResponse)
def restore_match(
    match_id: int,
    db: DbSession,
    user: CurrentUser,
    body: Optional[VLookupReviewBody] = None,
) -> VLookupActionResponse:
    payload = body or VLookupReviewBody()
    if not payload.reviewed_by:
        payload.reviewed_by = getattr(user, "email", None) or str(user.id)
    return vlookup_service.restore_match(db, match_id, payload)


@router.post("/matches/{match_id}/rematch", response_model=VLookupActionResponse)
def rematch(
    match_id: int,
    body: VLookupRematchBody,
    db: DbSession,
    user: CurrentUser,
) -> VLookupActionResponse:
    if not body.reviewed_by:
        body.reviewed_by = getattr(user, "email", None) or str(user.id)
    return vlookup_service.rematch(db, match_id, body)


@router.get("/download")
def download(
    db: DbSession,
    user: CurrentUser,
    batch_id: Optional[str] = Query(None),
    include_review_pending: bool = Query(False),
    month: Optional[str] = Query(None, description="YYYY-MM month to export hours for"),
) -> StreamingResponse:
    _ = user
    return vlookup_service.download_matches(
        db,
        batch_id=batch_id,
        include_review_pending=include_review_pending,
        month_key=month,
    )


@router.post("/publish-hours", response_model=VLookupPublishHoursResponse)
def publish_hours(
    db: DbSession,
    user: CurrentUser,
    batch_id: Optional[str] = Query(None),
    division: Optional[str] = Query(None),
    include_review_pending: bool = Query(False),
    month: Optional[str] = Query(None, description="YYYY-MM month to publish hours for"),
) -> VLookupPublishHoursResponse:
    """Persist matched VLOOKUP rows into hours_data_versions / hours_rows (DB source of truth)."""
    return vlookup_service.publish_hours_from_batch(
        db,
        batch_id=batch_id,
        division=division,
        include_review_pending=include_review_pending,
        month_key=month,
        uploaded_by=user.id,
    )
