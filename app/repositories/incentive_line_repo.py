from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.incentive_line import IncentiveApproval, IncentiveLine, IncentivePayment
from app.models.paid_ledger import PaidIncentiveLedger


def get_line(db: Session, line_id: int) -> Optional[IncentiveLine]:
    return db.query(IncentiveLine).filter(IncentiveLine.id == line_id).first()


def list_lines(db: Session, cycle_id: int) -> List[IncentiveLine]:
    return db.query(IncentiveLine).filter(IncentiveLine.cycle_id == cycle_id).all()


def add_approval(db: Session, **kwargs) -> IncentiveApproval:
    row = IncentiveApproval(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_payment_for_line(db: Session, line_id: int) -> Optional[IncentivePayment]:
    return (
        db.query(IncentivePayment)
        .filter(IncentivePayment.incentive_line_id == line_id)
        .first()
    )


def create_payment(db: Session, **kwargs) -> IncentivePayment:
    row = IncentivePayment(**kwargs)
    db.add(row)
    db.flush()
    return row


def create_ledger(db: Session, **kwargs) -> PaidIncentiveLedger:
    row = PaidIncentiveLedger(**kwargs)
    db.add(row)
    db.flush()
    return row


def ledger_key_exists(db: Session, dedupe_key: str) -> bool:
    return (
        db.query(PaidIncentiveLedger)
        .filter(PaidIncentiveLedger.dedupe_key == dedupe_key)
        .first()
        is not None
    )
