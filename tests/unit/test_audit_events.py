"""Focused audit event wiring for cycle hours upload and calculation."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.entities.audit import AuditAction, AuditLog
from app.repositories.entities.candidate import Candidate, CandidateDataVersion
from app.repositories.entities.cycle import CycleStatus, IncentiveCycle
from app.services.cycles.cycle_service import calculate_cycle, upload_hours_file


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_hours_file_writes_file_upload():
    db = _session()
    cycle = IncentiveCycle(
        name="Nashik Aug",
        division="nashik",
        incentive_month="2026-08",
        cycle_start_date=date(2026, 8, 1),
        cycle_end_date=date(2026, 8, 31),
        status=CycleStatus.DRAFT,
    )
    db.add(cycle)
    db.commit()

    content = _xlsx_bytes(
        ["Candidate ID", "Candidate Name", "Client Name", "Hours Worked", "Month"],
        [["12345", "Aisha Mayes", "Acme", 160, "2026-08"]],
    )
    upload_hours_file(db, cycle.id, "hours.xlsx", content)

    logs = db.query(AuditLog).filter(AuditLog.action == AuditAction.FILE_UPLOAD).all()
    assert logs
    assert any("hours.xlsx" in (row.details or "") for row in logs)
    assert any(row.entity_id == str(cycle.id) for row in logs)


def test_calculate_cycle_writes_calculation_run():
    db = _session()
    version = CandidateDataVersion(version_label="v1", division="nashik")
    db.add(version)
    db.flush()
    db.add(
        Candidate(
            external_candidate_id="12345",
            start_id="12345",
            candidate_name="Aisha Mayes",
            normalized_name="aisha mayes",
            contract_type="C2C",
            margin=Decimal("12"),
            recruiter="Amit William Ohol",
            team_lead="Majid Khan",
            manager="Nitin Giri",
            crm="David",
            center_head="ABC",
            avp="DEF",
            organization="Ampcus Inc",
            candidate_source="Ampcus Inc",
            recruiter_location="Nashik",
            start_date=date(2026, 1, 1),
            division="nashik",
            source_version_id=version.id,
            last_touched_version_id=version.id,
            incentive_active=True,
            is_active=True,
        )
    )
    cycle = IncentiveCycle(
        name="Nashik Aug",
        division="nashik",
        incentive_month="2026-08",
        cycle_start_date=date(2026, 8, 1),
        cycle_end_date=date(2026, 8, 31),
        status=CycleStatus.DRAFT,
    )
    db.add(cycle)
    db.commit()

    content = _xlsx_bytes(
        ["Candidate ID", "Candidate Name", "Client Name", "Hours Worked", "Month"],
        [["12345", "Aisha Mayes", "Acme", 160, "2026-08"]],
    )
    upload_hours_file(db, cycle.id, "hours.xlsx", content)
    calculate_cycle(db, cycle.id)

    logs = db.query(AuditLog).filter(AuditLog.action == AuditAction.CALCULATION_RUN).all()
    assert logs
    assert any("2026-08" in row.title for row in logs)
