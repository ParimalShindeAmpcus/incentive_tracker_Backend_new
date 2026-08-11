from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.cycle import (
    CycleChecklistItem,
    CycleDataSnapshot,
    CycleHoursMatch,
    CycleManualAdjustment,
    CyclePaymentStatus,
    CycleValidationResult,
    IncentiveCycle,
)
from app.models.incentive_line import IncentiveLine


def create_cycle(db: Session, **kwargs) -> IncentiveCycle:
    row = IncentiveCycle(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_cycle(db: Session, cycle_id: int) -> Optional[IncentiveCycle]:
    return db.query(IncentiveCycle).filter(IncentiveCycle.id == cycle_id).first()


def list_cycles(db: Session, *, offset: int = 0, limit: int = 50) -> List[IncentiveCycle]:
    return (
        db.query(IncentiveCycle)
        .order_by(IncentiveCycle.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_cycles(db: Session) -> int:
    return db.query(IncentiveCycle).count()


def update_cycle(db: Session, cycle: IncentiveCycle, **kwargs) -> IncentiveCycle:
    for k, v in kwargs.items():
        if v is not None:
            setattr(cycle, k, v)
    db.flush()
    return cycle


def delete_cycle(db: Session, cycle: IncentiveCycle) -> None:
    db.delete(cycle)
    db.flush()


def add_snapshot(db: Session, **kwargs) -> CycleDataSnapshot:
    row = CycleDataSnapshot(**kwargs)
    db.add(row)
    db.flush()
    return row


def clear_matches(db: Session, cycle_id: int) -> None:
    db.query(CycleHoursMatch).filter(CycleHoursMatch.cycle_id == cycle_id).delete()
    db.flush()


def add_match(db: Session, **kwargs) -> CycleHoursMatch:
    row = CycleHoursMatch(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_matches(db: Session, cycle_id: int) -> List[CycleHoursMatch]:
    return db.query(CycleHoursMatch).filter(CycleHoursMatch.cycle_id == cycle_id).all()


def get_match(db: Session, cycle_id: int, match_id: int) -> Optional[CycleHoursMatch]:
    return (
        db.query(CycleHoursMatch)
        .filter(CycleHoursMatch.cycle_id == cycle_id, CycleHoursMatch.id == match_id)
        .first()
    )


def clear_validations(db: Session, cycle_id: int) -> None:
    db.query(CycleValidationResult).filter(CycleValidationResult.cycle_id == cycle_id).delete()
    db.flush()


def add_validation(db: Session, **kwargs) -> CycleValidationResult:
    row = CycleValidationResult(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_validations(db: Session, cycle_id: int) -> List[CycleValidationResult]:
    return db.query(CycleValidationResult).filter(CycleValidationResult.cycle_id == cycle_id).all()


def get_checklist_item(
    db: Session, cycle_id: int, item_key: str
) -> Optional[CycleChecklistItem]:
    return (
        db.query(CycleChecklistItem)
        .filter(CycleChecklistItem.cycle_id == cycle_id, CycleChecklistItem.item_key == item_key)
        .first()
    )


def upsert_checklist(
    db: Session, cycle_id: int, item_key: str, **kwargs
) -> CycleChecklistItem:
    item = get_checklist_item(db, cycle_id, item_key)
    if not item:
        item = CycleChecklistItem(cycle_id=cycle_id, item_key=item_key, **kwargs)
        db.add(item)
    else:
        for k, v in kwargs.items():
            setattr(item, k, v)
    db.flush()
    return item


def list_payment_statuses(db: Session, cycle_id: int) -> List[CyclePaymentStatus]:
    return db.query(CyclePaymentStatus).filter(CyclePaymentStatus.cycle_id == cycle_id).all()


def upsert_payment_status(
    db: Session, cycle_id: int, candidate_id: int, **kwargs
) -> CyclePaymentStatus:
    row = (
        db.query(CyclePaymentStatus)
        .filter(
            CyclePaymentStatus.cycle_id == cycle_id,
            CyclePaymentStatus.candidate_id == candidate_id,
        )
        .first()
    )
    if not row:
        row = CyclePaymentStatus(cycle_id=cycle_id, candidate_id=candidate_id, **kwargs)
        db.add(row)
    else:
        for k, v in kwargs.items():
            setattr(row, k, v)
    db.flush()
    return row


def list_adjustments(db: Session, cycle_id: int) -> List[CycleManualAdjustment]:
    return db.query(CycleManualAdjustment).filter(CycleManualAdjustment.cycle_id == cycle_id).all()


def add_adjustment(db: Session, **kwargs) -> CycleManualAdjustment:
    row = CycleManualAdjustment(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_adjustment(db: Session, cycle_id: int, adjustment_id: int) -> Optional[CycleManualAdjustment]:
    return (
        db.query(CycleManualAdjustment)
        .filter(
            CycleManualAdjustment.cycle_id == cycle_id,
            CycleManualAdjustment.id == adjustment_id,
        )
        .first()
    )


def delete_adjustment(db: Session, row: CycleManualAdjustment) -> None:
    db.delete(row)
    db.flush()


def clear_lines(db: Session, cycle_id: int) -> None:
    db.query(IncentiveLine).filter(IncentiveLine.cycle_id == cycle_id).delete()
    db.flush()


def add_line(db: Session, **kwargs) -> IncentiveLine:
    row = IncentiveLine(**kwargs)
    db.add(row)
    db.flush()
    return row


def list_lines(db: Session, cycle_id: int) -> List[IncentiveLine]:
    return db.query(IncentiveLine).filter(IncentiveLine.cycle_id == cycle_id).all()
