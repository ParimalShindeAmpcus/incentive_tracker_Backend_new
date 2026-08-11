from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.cycle import CycleCreate, CycleOut, CycleSummary, CycleUpdate
from app.schemas.incentive import IncentiveLineOut
from app.services import cycle_service

router = APIRouter(prefix="/cycles", tags=["cycles"])


@router.get("")
def list_cycles(
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    return cycle_service.list_cycles(db, page=page, page_size=page_size)


@router.post("", response_model=CycleOut)
def create_cycle(
    payload: CycleCreate,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return cycle_service.create_cycle(db, user, payload)


@router.get("/{cycle_id}", response_model=CycleOut)
def get_cycle(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    return cycle_service.get_cycle(db, cycle_id)


@router.put("/{cycle_id}", response_model=CycleOut)
def update_cycle(
    cycle_id: int,
    payload: CycleUpdate,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return cycle_service.update_cycle(db, cycle_id, user, payload)


@router.delete("/{cycle_id}")
def delete_cycle(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    cycle_service.delete_cycle(db, cycle_id, user)
    return {"success": True}


@router.get("/{cycle_id}/summary", response_model=CycleSummary)
def cycle_summary(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    return cycle_service.summary(db, cycle_id)


@router.get("/{cycle_id}/lines", response_model=list[IncentiveLineOut])
def cycle_lines(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER")),
):
    from app.repositories import cycle_repo

    cycle_service.get_cycle(db, cycle_id)
    return cycle_repo.list_lines(db, cycle_id)
