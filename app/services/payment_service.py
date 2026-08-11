from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicatePaymentError, NotFoundError, ValidationAppError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import incentive_line_repo
from app.services import audit_service
from app.services.duplicate_service import paid_dedupe_key


def pay_line(db: Session, line_id: int, user: User, *, payment_reference: str | None = None, notes: str | None = None):
    line = incentive_line_repo.get_line(db, line_id)
    if not line:
        raise NotFoundError(f"Incentive line {line_id} not found")
    if not line.eligible:
        raise ValidationAppError("Cannot pay ineligible incentive line")
    existing = incentive_line_repo.get_payment_for_line(db, line_id)
    if existing:
        raise DuplicatePaymentError(details={"incentive_line_id": line_id, "payment_id": existing.id})

    dedupe = paid_dedupe_key(
        candidate_id=line.candidate_id,
        role=line.role,
        person=line.person,
        incentive_type=line.incentive_type,
    )
    try:
        payment = incentive_line_repo.create_payment(
            db,
            incentive_line_id=line.id,
            amount=line.amount,
            payment_reference=payment_reference,
            paid_by=user.id,
            status="PAID",
            notes=notes,
        )
        incentive_line_repo.create_ledger(
            db,
            payment_id=payment.id,
            cycle_id=line.cycle_id,
            candidate_id=line.candidate_id,
            role=line.role,
            person=line.person,
            incentive_type=line.incentive_type,
            amount=line.amount,
            dedupe_key=f"{dedupe}|cycle:{line.cycle_id}|line:{line.id}",
        )
        line.payment_status = "PAID"
        audit_service.write(
            db,
            action=AuditAction.PAYMENT,
            user_id=user.id,
            entity_type="incentive_payment",
            entity_id=str(payment.id),
            details=f"Paid line {line.id} amount={line.amount}",
        )
        db.commit()
        db.refresh(payment)
        return payment
    except IntegrityError as exc:
        db.rollback()
        raise DuplicatePaymentError(details={"incentive_line_id": line_id}) from exc
