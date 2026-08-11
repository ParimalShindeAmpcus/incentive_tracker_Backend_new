from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.audit import AuditAction
from app.models.cycle import CycleStatus
from app.models.user import User
from app.repositories import cycle_repo, incentive_line_repo
from app.services import audit_service, payment_service


def approve_cycle(db: Session, cycle_id: int, user: User, *, comments: str | None = None, pay: bool = False):
    cycle = cycle_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError(f"Cycle {cycle_id} not found")
    if cycle.status not in {CycleStatus.CALCULATED, CycleStatus.APPROVED}:
        raise ValidationAppError("Cycle must be CALCULATED before approval")

    lines = cycle_repo.list_lines(db, cycle_id)
    for line in lines:
        if not line.eligible:
            continue
        incentive_line_repo.add_approval(
            db,
            incentive_line_id=line.id,
            action="APPROVE",
            approved_by=user.id,
            comments=comments,
        )
        if line.payment_status == "UNPAID":
            line.payment_status = "APPROVED"

    cycle.status = CycleStatus.APPROVED
    audit_service.write(
        db,
        action=AuditAction.APPROVAL,
        user_id=user.id,
        entity_type="incentive_cycle",
        entity_id=str(cycle.id),
        details=comments or "Cycle approved",
    )
    db.commit()

    paid = []
    if pay:
        for line in cycle_repo.list_lines(db, cycle_id):
            if line.eligible and line.payment_status in {"APPROVED", "UNPAID"}:
                try:
                    paid.append(payment_service.pay_line(db, line.id, user))
                except Exception:
                    db.rollback()
                    raise
        cycle = cycle_repo.get_cycle(db, cycle_id)
        if cycle:
            cycle.status = CycleStatus.PAID
            db.commit()
    return {"cycle": cycle_repo.get_cycle(db, cycle_id), "payments": paid}
