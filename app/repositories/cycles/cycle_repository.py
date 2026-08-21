"""Cycle repository — SQL only."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.repositories.entities.cycle import (
    CycleApprovalResult,
    CycleChecklistItem,
    CycleHoursMatch,
    CycleManualAdjustment,
    CyclePaymentStatus,
    CycleStatus,
    CycleValidationResult,
    IncentiveCycle,
    MatchResult,
)
from app.repositories.entities.incentive import IncentiveLine


def create_cycle(db: Session, data: dict) -> IncentiveCycle:
    cycle = IncentiveCycle(**data)
    db.add(cycle)
    db.flush()
    return cycle


def list_cycles(
    db: Session,
    *,
    division: Optional[str] = None,
    status: Optional[str] = None,
) -> List[IncentiveCycle]:
    q = db.query(IncentiveCycle)
    if division:
        q = q.filter(IncentiveCycle.division == division)
    if status:
        q = q.filter(IncentiveCycle.status == CycleStatus(status))
    return q.order_by(IncentiveCycle.id.desc()).all()


def get_cycle(db: Session, cycle_id: int) -> Optional[IncentiveCycle]:
    return db.query(IncentiveCycle).filter(IncentiveCycle.id == cycle_id).first()


def update_cycle(db: Session, cycle: IncentiveCycle, data: dict) -> IncentiveCycle:
    for key, value in data.items():
        if key == "status" and value is not None:
            setattr(cycle, key, CycleStatus(value) if isinstance(value, str) else value)
        else:
            setattr(cycle, key, value)
    db.add(cycle)
    db.flush()
    return cycle


def delete_cycle(db: Session, cycle: IncentiveCycle) -> None:
    db.delete(cycle)
    db.flush()


def list_matches(db: Session, cycle_id: int) -> List[CycleHoursMatch]:
    return (
        db.query(CycleHoursMatch)
        .filter(CycleHoursMatch.cycle_id == cycle_id)
        .order_by(CycleHoursMatch.id)
        .all()
    )


def get_match(db: Session, match_id: int) -> Optional[CycleHoursMatch]:
    return db.query(CycleHoursMatch).filter(CycleHoursMatch.id == match_id).first()


def update_match(db: Session, match: CycleHoursMatch, data: dict) -> CycleHoursMatch:
    for key, value in data.items():
        if key == "match_result" and value is not None:
            setattr(match, key, MatchResult(value) if isinstance(value, str) else value)
        else:
            setattr(match, key, value)
    db.add(match)
    db.flush()
    return match


def list_validations(db: Session, cycle_id: int) -> List[CycleValidationResult]:
    return (
        db.query(CycleValidationResult)
        .filter(CycleValidationResult.cycle_id == cycle_id)
        .order_by(CycleValidationResult.id)
        .all()
    )


def list_checklist(db: Session, cycle_id: int) -> List[CycleChecklistItem]:
    return (
        db.query(CycleChecklistItem)
        .filter(CycleChecklistItem.cycle_id == cycle_id)
        .order_by(CycleChecklistItem.id)
        .all()
    )


def get_checklist_item(db: Session, item_id: int) -> Optional[CycleChecklistItem]:
    return db.query(CycleChecklistItem).filter(CycleChecklistItem.id == item_id).first()


def update_checklist_item(
    db: Session,
    item: CycleChecklistItem,
    *,
    is_checked: bool,
    notes: Optional[str],
    checked_by: Optional[int],
) -> CycleChecklistItem:
    item.is_checked = is_checked
    if notes is not None:
        item.notes = notes
    item.checked_by = checked_by
    item.checked_at = datetime.now(timezone.utc) if is_checked else None
    db.add(item)
    db.flush()
    return item


def ensure_default_checklist(db: Session, cycle_id: int) -> List[CycleChecklistItem]:
    existing = list_checklist(db, cycle_id)
    if existing:
        return existing
    defaults = [
        ("data_uploaded", "Source data uploaded"),
        ("matches_reviewed", "Matches reviewed"),
        ("validations_cleared", "Validations cleared"),
        ("calculations_reviewed", "Calculations reviewed"),
    ]
    items = []
    for key, label in defaults:
        item = CycleChecklistItem(cycle_id=cycle_id, item_key=key, label=label, is_checked=False)
        db.add(item)
        items.append(item)
    db.flush()
    return items


def list_payment_statuses(db: Session, cycle_id: int) -> List[CyclePaymentStatus]:
    return (
        db.query(CyclePaymentStatus)
        .filter(CyclePaymentStatus.cycle_id == cycle_id)
        .order_by(CyclePaymentStatus.id)
        .all()
    )


def clear_payment_statuses(db: Session, cycle_id: int) -> None:
    db.query(CyclePaymentStatus).filter(CyclePaymentStatus.cycle_id == cycle_id).delete(
        synchronize_session=False
    )
    db.flush()


def ensure_payment_statuses(db: Session, cycle_id: int, candidate_ids: List[int]) -> List[CyclePaymentStatus]:
    existing = {row.candidate_id for row in list_payment_statuses(db, cycle_id)}
    created = []
    for candidate_id in candidate_ids:
        if candidate_id not in existing:
            row = CyclePaymentStatus(cycle_id=cycle_id, candidate_id=candidate_id, status="PAYMENT_PENDING")
            db.add(row)
            created.append(row)
    db.flush()
    return created


def sync_payment_statuses(db: Session, cycle_id: int, candidate_ids: List[int]) -> List[CyclePaymentStatus]:
    existing = {row.candidate_id: row for row in list_payment_statuses(db, cycle_id)}
    target_ids = set(candidate_ids)
    for cand_id, row in existing.items():
        if cand_id not in target_ids:
            db.delete(row)
    created = []
    for candidate_id in target_ids:
        if candidate_id not in existing:
            new_row = CyclePaymentStatus(cycle_id=cycle_id, candidate_id=candidate_id, status="PAYMENT_PENDING")
            db.add(new_row)
            created.append(new_row)
    db.flush()
    return created


def get_payment_status(db: Session, status_id: int) -> Optional[CyclePaymentStatus]:
    return db.query(CyclePaymentStatus).filter(CyclePaymentStatus.id == status_id).first()


def update_payment_status(
    db: Session,
    row: CyclePaymentStatus,
    *,
    status: str,
    payment_received_date=None,
    payment_reference: Optional[str] = None,
    notes: Optional[str],
    updated_by: Optional[int],
) -> CyclePaymentStatus:
    row.status = status
    if payment_received_date is not None:
        row.payment_received_date = payment_received_date
    if payment_reference is not None:
        row.payment_reference = payment_reference
    if notes is not None:
        row.notes = notes
    row.updated_by = updated_by
    db.add(row)
    db.flush()
    return row


def list_adjustments(db: Session, cycle_id: int) -> List[CycleManualAdjustment]:
    return (
        db.query(CycleManualAdjustment)
        .filter(CycleManualAdjustment.cycle_id == cycle_id)
        .order_by(CycleManualAdjustment.id)
        .all()
    )


def create_adjustment(db: Session, data: dict) -> CycleManualAdjustment:
    row = CycleManualAdjustment(**data)
    db.add(row)
    db.flush()
    return row


def list_lines(db: Session, cycle_id: int) -> List[IncentiveLine]:
    return (
        db.query(IncentiveLine)
        .filter(IncentiveLine.cycle_id == cycle_id)
        .order_by(IncentiveLine.id)
        .all()
    )


def replace_matches(db: Session, cycle_id: int, rows: List[dict]) -> List[CycleHoursMatch]:
    db.query(CycleHoursMatch).filter(CycleHoursMatch.cycle_id == cycle_id).delete(synchronize_session=False)
    created: List[CycleHoursMatch] = []
    for data in rows:
        payload = dict(data)
        raw_result = payload.get("match_result")
        if isinstance(raw_result, str):
            payload["match_result"] = MatchResult(raw_result)
        row = CycleHoursMatch(cycle_id=cycle_id, **payload)
        db.add(row)
        created.append(row)
    db.flush()
    return created


def replace_validations(db: Session, cycle_id: int, rows: List[dict]) -> List[CycleValidationResult]:
    db.query(CycleValidationResult).filter(CycleValidationResult.cycle_id == cycle_id).delete(
        synchronize_session=False
    )
    created: List[CycleValidationResult] = []
    for data in rows:
        row = CycleValidationResult(cycle_id=cycle_id, **data)
        db.add(row)
        created.append(row)
    db.flush()
    return created


def summary_counts(db: Session, cycle_id: int) -> dict:
    match_count = db.query(func.count(CycleHoursMatch.id)).filter(CycleHoursMatch.cycle_id == cycle_id).scalar() or 0
    validation_count = (
        db.query(func.count(CycleValidationResult.id)).filter(CycleValidationResult.cycle_id == cycle_id).scalar() or 0
    )
    checklist_total = (
        db.query(func.count(CycleChecklistItem.id)).filter(CycleChecklistItem.cycle_id == cycle_id).scalar() or 0
    )
    checklist_checked = (
        db.query(func.count(CycleChecklistItem.id))
        .filter(CycleChecklistItem.cycle_id == cycle_id, CycleChecklistItem.is_checked.is_(True))
        .scalar()
        or 0
    )
    line_count = db.query(func.count(IncentiveLine.id)).filter(IncentiveLine.cycle_id == cycle_id).scalar() or 0
    total_amount = (
        db.query(func.coalesce(func.sum(IncentiveLine.amount), 0))
        .filter(IncentiveLine.cycle_id == cycle_id)
        .scalar()
    )
    return {
        "match_count": match_count,
        "validation_count": validation_count,
        "checklist_total": checklist_total,
        "checklist_checked": checklist_checked,
        "line_count": line_count,
        "total_amount": Decimal(str(total_amount or 0)),
    }


def list_approval_results(db: Session, cycle_id: int) -> List[CycleApprovalResult]:
    return (
        db.query(CycleApprovalResult)
        .filter(CycleApprovalResult.cycle_id == cycle_id)
        .order_by(CycleApprovalResult.id)
        .all()
    )


def has_approval_results(db: Session, cycle_id: int) -> bool:
    return (
        db.query(CycleApprovalResult.id)
        .filter(CycleApprovalResult.cycle_id == cycle_id)
        .first()
        is not None
    )


def list_completed_cycles_missing_approval_results(db: Session) -> List[IncentiveCycle]:
    completed = {CycleStatus.APPROVED, CycleStatus.PAID, CycleStatus.CLOSED}
    subq = db.query(CycleApprovalResult.cycle_id).distinct()
    return (
        db.query(IncentiveCycle)
        .filter(IncentiveCycle.status.in_(completed), ~IncentiveCycle.id.in_(subq))
        .order_by(IncentiveCycle.id)
        .all()
    )


def replace_approval_results(
    db: Session, cycle_id: int, rows: List[dict]
) -> List[CycleApprovalResult]:
    db.query(CycleApprovalResult).filter(CycleApprovalResult.cycle_id == cycle_id).delete(
        synchronize_session=False
    )
    created: List[CycleApprovalResult] = []
    for data in rows:
        row = CycleApprovalResult(cycle_id=cycle_id, **data)
        db.add(row)
        created.append(row)
    db.flush()
    return created
