from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import cycle_repo
from app.services import audit_service


def list_adjustments(db: Session, cycle_id: int):
    if not cycle_repo.get_cycle(db, cycle_id):
        raise NotFoundError(f"Cycle {cycle_id} not found")
    return cycle_repo.list_adjustments(db, cycle_id)


def create_adjustment(db: Session, cycle_id: int, user: User, payload: dict):
    if not cycle_repo.get_cycle(db, cycle_id):
        raise NotFoundError(f"Cycle {cycle_id} not found")
    row = cycle_repo.add_adjustment(db, cycle_id=cycle_id, created_by=user.id, **payload)
    audit_service.write(
        db,
        action=AuditAction.ADJUSTMENT,
        user_id=user.id,
        entity_type="cycle_manual_adjustment",
        entity_id=str(row.id),
        details=f"Adjustment {payload.get('kind')} amount={payload.get('amount')}",
    )
    db.commit()
    db.refresh(row)
    return row


def delete_adjustment(db: Session, cycle_id: int, adjustment_id: int, user: User):
    row = cycle_repo.get_adjustment(db, cycle_id, adjustment_id)
    if not row:
        raise NotFoundError(f"Adjustment {adjustment_id} not found")
    cycle_repo.delete_adjustment(db, row)
    audit_service.write(
        db,
        action=AuditAction.DELETE,
        user_id=user.id,
        entity_type="cycle_manual_adjustment",
        entity_id=str(adjustment_id),
        details="Deleted manual adjustment",
    )
    db.commit()
