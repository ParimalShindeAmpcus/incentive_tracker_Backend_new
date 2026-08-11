"""Cycle service — orchestration."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cycles.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    ApproveRequest,
    ChecklistOut,
    ChecklistUpdate,
    CycleCreate,
    CycleOut,
    CycleSummary,
    CycleUpdate,
    MatchOut,
    MatchUpdate,
    PaymentStatusOut,
    PaymentStatusUpdate,
    ValidationOut,
)
from app.models.incentives.schemas import IncentiveLineOut
from app.repositories.cycles import cycle_repository
from app.repositories.entities.cycle import CycleStatus


def create_cycle(db: Session, payload: CycleCreate, created_by: Optional[int] = None) -> CycleOut:
    data = payload.model_dump()
    data["created_by"] = created_by
    data["status"] = CycleStatus.DRAFT
    cycle = cycle_repository.create_cycle(db, data)
    cycle_repository.ensure_default_checklist(db, cycle.id)
    db.commit()
    db.refresh(cycle)
    return CycleOut.model_validate(cycle)


def list_cycles(
    db: Session,
    *,
    division: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> List[CycleOut]:
    rows = cycle_repository.list_cycles(db, division=division, status=status_filter)
    return [CycleOut.model_validate(r) for r in rows]


def get_cycle(db: Session, cycle_id: int) -> CycleOut:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    return CycleOut.model_validate(cycle)


def update_cycle(db: Session, cycle_id: int, payload: CycleUpdate) -> CycleOut:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    updated = cycle_repository.update_cycle(db, cycle, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(updated)
    return CycleOut.model_validate(updated)


def delete_cycle(db: Session, cycle_id: int) -> dict:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    cycle_repository.delete_cycle(db, cycle)
    db.commit()
    return {"message": "deleted", "id": cycle_id}


def get_summary(db: Session, cycle_id: int) -> CycleSummary:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    counts = cycle_repository.summary_counts(db, cycle_id)
    status_val = cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status)
    return CycleSummary(cycle_id=cycle_id, status=status_val, **counts)


def list_lines(db: Session, cycle_id: int) -> List[IncentiveLineOut]:
    _require_cycle(db, cycle_id)
    rows = cycle_repository.list_lines(db, cycle_id)
    return [IncentiveLineOut.model_validate(r) for r in rows]


def list_matches(db: Session, cycle_id: int) -> List[MatchOut]:
    _require_cycle(db, cycle_id)
    return [MatchOut.model_validate(r) for r in cycle_repository.list_matches(db, cycle_id)]


def update_match(db: Session, cycle_id: int, match_id: int, payload: MatchUpdate) -> MatchOut:
    _require_cycle(db, cycle_id)
    match = cycle_repository.get_match(db, match_id)
    if match is None or match.cycle_id != cycle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    updated = cycle_repository.update_match(db, match, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(updated)
    return MatchOut.model_validate(updated)


def list_validations(db: Session, cycle_id: int) -> List[ValidationOut]:
    _require_cycle(db, cycle_id)
    return [ValidationOut.model_validate(r) for r in cycle_repository.list_validations(db, cycle_id)]


def list_checklist(db: Session, cycle_id: int) -> List[ChecklistOut]:
    _require_cycle(db, cycle_id)
    items = cycle_repository.ensure_default_checklist(db, cycle_id)
    db.commit()
    return [ChecklistOut.model_validate(r) for r in items]


def update_checklist(
    db: Session,
    cycle_id: int,
    item_id: int,
    payload: ChecklistUpdate,
    user_id: Optional[int] = None,
) -> ChecklistOut:
    _require_cycle(db, cycle_id)
    item = cycle_repository.get_checklist_item(db, item_id)
    if item is None or item.cycle_id != cycle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    updated = cycle_repository.update_checklist_item(
        db,
        item,
        is_checked=payload.is_checked,
        notes=payload.notes,
        checked_by=user_id,
    )
    db.commit()
    db.refresh(updated)
    return ChecklistOut.model_validate(updated)


def list_payment_statuses(db: Session, cycle_id: int) -> List[PaymentStatusOut]:
    _require_cycle(db, cycle_id)
    return [PaymentStatusOut.model_validate(r) for r in cycle_repository.list_payment_statuses(db, cycle_id)]


def update_payment_status(
    db: Session,
    cycle_id: int,
    status_id: int,
    payload: PaymentStatusUpdate,
    user_id: Optional[int] = None,
) -> PaymentStatusOut:
    _require_cycle(db, cycle_id)
    row = cycle_repository.get_payment_status(db, status_id)
    if row is None or row.cycle_id != cycle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment status not found")
    updated = cycle_repository.update_payment_status(
        db,
        row,
        status=payload.status,
        notes=payload.notes,
        updated_by=user_id,
    )
    db.commit()
    db.refresh(updated)
    return PaymentStatusOut.model_validate(updated)


def list_adjustments(db: Session, cycle_id: int) -> List[AdjustmentOut]:
    _require_cycle(db, cycle_id)
    return [AdjustmentOut.model_validate(r) for r in cycle_repository.list_adjustments(db, cycle_id)]


def create_adjustment(
    db: Session,
    cycle_id: int,
    payload: AdjustmentCreate,
    created_by: Optional[int] = None,
) -> AdjustmentOut:
    _require_cycle(db, cycle_id)
    data = payload.model_dump()
    data["cycle_id"] = cycle_id
    data["created_by"] = created_by
    row = cycle_repository.create_adjustment(db, data)
    db.commit()
    db.refresh(row)
    return AdjustmentOut.model_validate(row)


def approve_cycle(
    db: Session,
    cycle_id: int,
    payload: ApproveRequest,
    user_id: Optional[int] = None,
) -> CycleOut:
    cycle = _require_cycle(db, cycle_id)
    cycle.status = CycleStatus.APPROVED
    cycle.approved_at = datetime.now(timezone.utc)
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return CycleOut.model_validate(cycle)


def calculate_cycle(db: Session, cycle_id: int) -> CycleOut:
    """Stub: flip status to CALCULATED without running the full engine."""
    cycle = _require_cycle(db, cycle_id)
    cycle.status = CycleStatus.CALCULATED
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return CycleOut.model_validate(cycle)


def export_cycle_stub(db: Session, cycle_id: int) -> dict:
    _require_cycle(db, cycle_id)
    return {"message": "not implemented", "cycle_id": cycle_id}


def _require_cycle(db: Session, cycle_id: int):
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    return cycle
