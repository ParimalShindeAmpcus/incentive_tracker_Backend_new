from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.cycle import (
    AdjustmentCreate,
    AdjustmentOut,
    ApproveRequest,
    ChecklistOut,
    ChecklistUpdate,
    MatchOut,
    MatchUpdate,
    PaymentStatusOut,
    PaymentStatusUpdate,
    ValidationOut,
)
from app.services import adjustment_service, approval_service, cycle_service, validation_service
from app.repositories import cycle_repo

router = APIRouter(prefix="/cycles", tags=["cycle-workflow"])


@router.post("/{cycle_id}/calculate")
def calculate(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return cycle_service.calculate(db, cycle_id, user)


@router.post("/{cycle_id}/approve")
def approve(
    cycle_id: int,
    payload: ApproveRequest,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return approval_service.approve_cycle(
        db, cycle_id, user, comments=payload.comments, pay=payload.pay
    )


@router.get("/{cycle_id}/matches", response_model=list[MatchOut])
def list_matches(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    cycle_service.get_cycle(db, cycle_id)
    return cycle_repo.list_matches(db, cycle_id)


@router.patch("/{cycle_id}/matches/{match_id}", response_model=MatchOut)
def patch_match(
    cycle_id: int,
    match_id: int,
    payload: MatchUpdate,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return cycle_service.update_match(
        db, cycle_id, match_id, user, payload.model_dump(exclude_unset=True)
    )


@router.get("/{cycle_id}/validation", response_model=list[ValidationOut])
def get_validation(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    cycle = cycle_service.get_cycle(db, cycle_id)
    rows = cycle_repo.list_validations(db, cycle_id)
    if not rows:
        rows = validation_service.run_validation(db, cycle, user_id=user.id)
    return rows


@router.patch("/{cycle_id}/checklist/{key}", response_model=ChecklistOut)
def patch_checklist(
    cycle_id: int,
    key: str,
    payload: ChecklistUpdate,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return cycle_service.update_checklist(
        db, cycle_id, key, user, is_checked=payload.is_checked, notes=payload.notes
    )


@router.get("/{cycle_id}/payment-statuses", response_model=list[PaymentStatusOut])
def list_payment_statuses(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    cycle_service.get_cycle(db, cycle_id)
    return cycle_repo.list_payment_statuses(db, cycle_id)


@router.patch("/{cycle_id}/payment-statuses/{candidate_id}", response_model=PaymentStatusOut)
def patch_payment_status(
    cycle_id: int,
    candidate_id: int,
    payload: PaymentStatusUpdate,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return cycle_service.update_payment_status(
        db, cycle_id, candidate_id, user, status=payload.status, notes=payload.notes
    )


@router.get("/{cycle_id}/manual-adjustments", response_model=list[AdjustmentOut])
def list_adjustments(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    return adjustment_service.list_adjustments(db, cycle_id)


@router.post("/{cycle_id}/manual-adjustments", response_model=AdjustmentOut)
def create_adjustment(
    cycle_id: int,
    payload: AdjustmentCreate,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return adjustment_service.create_adjustment(
        db, cycle_id, user, payload.model_dump()
    )


@router.delete("/{cycle_id}/manual-adjustments/{adjustment_id}")
def delete_adjustment(
    cycle_id: int,
    adjustment_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    adjustment_service.delete_adjustment(db, cycle_id, adjustment_id, user)
    return {"success": True}
