"""Cycle HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, File, Query, UploadFile

from app.models.cycles.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    ApproveRequest,
    CalculateResult,
    ChecklistOut,
    ChecklistUpdate,
    CycleApprovalResultOut,
    CycleCreate,
    CycleOut,
    CycleSummary,
    CycleUpdate,
    HoursUploadOut,
    MatchOut,
    MatchUpdate,
    PaymentStatusOut,
    PaymentStatusUpdate,
    ValidationOut,
)
from app.models.incentives.schemas import IncentiveLineOut
from app.services.common.deps import CurrentUser, DbSession
from app.services.cycles import cycle_service

router = APIRouter()


@router.post("", response_model=CycleOut)
def create_cycle(payload: CycleCreate, db: DbSession, user: CurrentUser) -> CycleOut:
    return cycle_service.create_cycle(db, payload, created_by=user.id)


@router.get("", response_model=List[CycleOut])
def list_cycles(
    db: DbSession,
    division: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> List[CycleOut]:
    return cycle_service.list_cycles(db, division=division, status_filter=status)


@router.get("/{cycle_id}", response_model=CycleOut)
def get_cycle(cycle_id: int, db: DbSession) -> CycleOut:
    return cycle_service.get_cycle(db, cycle_id)


@router.patch("/{cycle_id}", response_model=CycleOut)
def patch_cycle(cycle_id: int, payload: CycleUpdate, db: DbSession) -> CycleOut:
    return cycle_service.update_cycle(db, cycle_id, payload)


@router.delete("/{cycle_id}")
def delete_cycle(cycle_id: int, db: DbSession) -> dict:
    return cycle_service.delete_cycle(db, cycle_id)


@router.get("/{cycle_id}/summary", response_model=CycleSummary)
def get_summary(cycle_id: int, db: DbSession) -> CycleSummary:
    return cycle_service.get_summary(db, cycle_id)


@router.get("/{cycle_id}/lines", response_model=List[IncentiveLineOut])
def get_lines(cycle_id: int, db: DbSession) -> List[IncentiveLineOut]:
    return cycle_service.list_lines(db, cycle_id)


@router.get("/{cycle_id}/matches", response_model=List[MatchOut])
def get_matches(cycle_id: int, db: DbSession) -> List[MatchOut]:
    return cycle_service.list_matches(db, cycle_id)


@router.patch("/{cycle_id}/matches/{match_id}", response_model=MatchOut)
def patch_match(cycle_id: int, match_id: int, payload: MatchUpdate, db: DbSession) -> MatchOut:
    return cycle_service.update_match(db, cycle_id, match_id, payload)


@router.get("/{cycle_id}/validations", response_model=List[ValidationOut])
def get_validations(cycle_id: int, db: DbSession) -> List[ValidationOut]:
    return cycle_service.list_validations(db, cycle_id)


@router.get("/{cycle_id}/checklist", response_model=List[ChecklistOut])
def get_checklist(cycle_id: int, db: DbSession) -> List[ChecklistOut]:
    return cycle_service.list_checklist(db, cycle_id)


@router.patch("/{cycle_id}/checklist/{item_id}", response_model=ChecklistOut)
def patch_checklist(
    cycle_id: int,
    item_id: int,
    payload: ChecklistUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ChecklistOut:
    return cycle_service.update_checklist(db, cycle_id, item_id, payload, user_id=user.id)


@router.get("/{cycle_id}/payment-statuses", response_model=List[PaymentStatusOut])
def get_payment_statuses(cycle_id: int, db: DbSession) -> List[PaymentStatusOut]:
    return cycle_service.list_payment_statuses(db, cycle_id)


@router.patch("/{cycle_id}/payment-statuses/{status_id}", response_model=PaymentStatusOut)
def patch_payment_status(
    cycle_id: int,
    status_id: int,
    payload: PaymentStatusUpdate,
    db: DbSession,
    user: CurrentUser,
) -> PaymentStatusOut:
    return cycle_service.update_payment_status(db, cycle_id, status_id, payload, user=user)


@router.get("/{cycle_id}/adjustments", response_model=List[AdjustmentOut])
def get_adjustments(cycle_id: int, db: DbSession) -> List[AdjustmentOut]:
    return cycle_service.list_adjustments(db, cycle_id)


@router.post("/{cycle_id}/adjustments", response_model=AdjustmentOut)
def post_adjustment(
    cycle_id: int,
    payload: AdjustmentCreate,
    db: DbSession,
    user: CurrentUser,
) -> AdjustmentOut:
    return cycle_service.create_adjustment(db, cycle_id, payload, created_by=user.id)


@router.post("/{cycle_id}/hours-upload", response_model=HoursUploadOut)
async def upload_hours(
    cycle_id: int,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> HoursUploadOut:
    content = await file.read()
    return cycle_service.upload_hours_file(db, cycle_id, file.filename or "hours.xlsx", content, user=user)


@router.post("/{cycle_id}/approve", response_model=CycleOut)
def approve(cycle_id: int, payload: ApproveRequest, db: DbSession, user: CurrentUser) -> CycleOut:
    return cycle_service.approve_cycle(db, cycle_id, payload, user=user)


@router.get("/{cycle_id}/approval-results", response_model=List[CycleApprovalResultOut])
def get_approval_results(cycle_id: int, db: DbSession) -> List[CycleApprovalResultOut]:
    return cycle_service.list_approval_results(db, cycle_id)


@router.post("/{cycle_id}/calculate", response_model=CalculateResult)
def calculate(cycle_id: int, db: DbSession, user: CurrentUser) -> CalculateResult:
    return cycle_service.calculate_cycle(db, cycle_id, user=user)


@router.get("/{cycle_id}/export")
def export_cycle(cycle_id: int, db: DbSession, user: CurrentUser):
    return cycle_service.export_cycle(db, cycle_id, user=user)
