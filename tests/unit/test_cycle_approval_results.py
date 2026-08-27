"""Frozen cycle_approval_results snapshot on approve."""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.cycles.schemas import ApproveRequest
from app.repositories.cycles import cycle_repository
from app.repositories.entities.audit import AuditAction, AuditLog
from app.repositories.entities.cycle import CycleApprovalResult, CycleStatus, IncentiveCycle
from app.repositories.entities.incentive import IncentiveLine
from app.repositories.reports.reports_repository import list_report_dicts
from app.services.cycles.cycle_service import (
    approve_cycle,
    backfill_missing_approval_results,
    snapshot_approval_results,
)


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _cycle(db, *, status=CycleStatus.CALCULATED) -> IncentiveCycle:
    cycle = IncentiveCycle(
        name="Nashik Aug",
        division="nashik",
        incentive_month="2026-08",
        cycle_start_date=date(2026, 8, 1),
        cycle_end_date=date(2026, 8, 31),
        status=status,
        created_by=None,
    )
    db.add(cycle)
    db.flush()
    return cycle


def _line(db, cycle: IncentiveCycle, *, eligible=True, amount="3500", person="Amit") -> IncentiveLine:
    row = IncentiveLine(
        cycle_id=cycle.id,
        candidate_name="Aisha Mayes",
        role="Recruiter",
        person=person,
        incentive_type="RECURRING",
        rule_applied="Nashik recruiter",
        eligible=eligible,
        base_incentive=Decimal(amount),
        pro_rata_factor=Decimal("1"),
        amount=Decimal(amount),
        hours=Decimal("160"),
        margin=Decimal("12"),
        payment_status="UNPAID",
    )
    db.add(row)
    db.flush()
    return row


def test_approve_cycle_writes_approval_results():
    db = _session()
    cycle = _cycle(db)
    _line(db, cycle)
    _line(db, cycle, eligible=False, amount="0", person="Excluded Person")

    out = approve_cycle(db, cycle.id, ApproveRequest(comments="ok"), user_id=None)
    assert out.status == "APPROVED"
    audit_rows = [row for row in db.query(AuditLog).all() if row.action == AuditAction.CYCLE_APPROVE]
    assert len(audit_rows) == 1
    assert "2026-08" in audit_rows[0].title

    rows = cycle_repository.list_approval_results(db, cycle.id)
    assert len(rows) == 2
    payout = next(r for r in rows if r.eligible)
    assert payout.cycle_name == "Nashik Aug"
    assert payout.division == "nashik"
    assert payout.incentive_month == "2026-08"
    assert payout.person == "Amit"
    assert payout.amount == Decimal("3500")
    assert payout.comments == "ok"
    assert db.query(CycleApprovalResult).count() == 2


def test_reapprove_replaces_snapshot_not_duplicates():
    db = _session()
    cycle = _cycle(db)
    _line(db, cycle)
    approve_cycle(db, cycle.id, ApproveRequest(), user_id=None)
    approve_cycle(db, cycle.id, ApproveRequest(comments="second"), user_id=None)
    rows = cycle_repository.list_approval_results(db, cycle.id)
    assert len(rows) == 1
    assert rows[0].comments == "second"


def test_backfill_snapshots_existing_approved_cycles():
    db = _session()
    cycle = _cycle(db, status=CycleStatus.APPROVED)
    cycle.approved_at = None
    _line(db, cycle)
    db.commit()

    assert cycle_repository.has_approval_results(db, cycle.id) is False
    filled = backfill_missing_approval_results(db)
    assert filled == 1
    assert cycle_repository.has_approval_results(db, cycle.id) is True
    assert backfill_missing_approval_results(db) == 0


def test_approved_reports_read_snapshot_not_live_lines():
    db = _session()
    cycle = _cycle(db, status=CycleStatus.APPROVED)
    line = _line(db, cycle, amount="3500")
    snapshot_approval_results(db, cycle)
    db.commit()

    line.amount = Decimal("1")
    db.add(line)
    db.commit()

    rows = list_report_dicts(db, approved_only=True)
    assert len(rows) == 1
    assert Decimal(str(rows[0]["amount"])) == Decimal("3500")
    assert rows[0]["cycle_id"] == cycle.id
    assert rows[0]["candidate_name"] == "Aisha Mayes"
