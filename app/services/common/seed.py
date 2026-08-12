"""Idempotent startup / create_db seed data."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.db import get_engine
from app.repositories.audit import audit_repository
from app.repositories.auth import auth_repository
from app.repositories.entities.audit import AuditAction
from app.repositories.hours import hours_repository
from app.repositories.incentives import incentive_repository
from app.repositories.organization import organization_repository
from app.security.auth import hash_password
from sqlalchemy.orm import sessionmaker


DIVISIONS = [
    ("nashik", "Nashik Division"),
    ("sambhajiNagar", "Sambhaji Nagar Division"),
    ("ampcusTechClient", "Ampcus Tech (Client)"),
    ("ampcusTechInhouse", "Ampcus Tech In-House"),
]

ROLE_DEFS = [
    ("ADMIN", "Full system administrator"),
    ("ACCOUNTS", "Accounts / payments operator"),
    ("VIEWER", "Read-only viewer"),
]


def seed_database(db: Optional[Session] = None) -> None:
    """Seed roles, default admin, DEFAULT org + divisions, benchmarks, sample slabs."""
    own_session = db is None
    if own_session:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
        db = SessionLocal()
    assert db is not None
    try:
        _seed_roles_and_admin(db)
        org = _seed_organization(db)
        _seed_divisions(db, org.id)
        _seed_hours_benchmarks(db)
        _seed_nashik_slabs(db)
        _seed_audit_logs(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


def _seed_roles_and_admin(db: Session) -> None:
    settings = get_settings()
    roles = {}
    for name, description in ROLE_DEFS:
        role = auth_repository.get_role_by_name(db, name)
        if role is None:
            role = auth_repository.create_role(db, name=name, description=description)
        roles[name] = role

    email = settings.default_admin_email.lower().strip()
    user = auth_repository.get_user_by_email(db, email)
    if user is None:
        auth_repository.create_user(
            db,
            email=email,
            full_name="Default Admin",
            hashed_password=hash_password(settings.default_admin_password),
            roles=[roles["ADMIN"], roles["ACCOUNTS"]],
            is_active=True,
        )


def _seed_organization(db: Session):
    org = organization_repository.get_organization_by_code(db, "DEFAULT")
    if org is None:
        org = organization_repository.create_organization(db, code="DEFAULT", name="Default Organization")
    return org


def _seed_divisions(db: Session, organization_id: int) -> None:
    for code, name in DIVISIONS:
        existing = organization_repository.get_division_by_code(db, organization_id, code)
        if existing is None:
            organization_repository.create_division(db, organization_id, code, name)


def _seed_hours_benchmarks(db: Session) -> None:
    for code, _name in DIVISIONS:
        existing = hours_repository.get_benchmark(db, code)
        if existing is None:
            hours_repository.upsert_benchmark(
                db,
                division=code,
                benchmark_hours=Decimal("160"),
                description=f"Default monthly hours benchmark for {code}",
                is_active=True,
            )


def _seed_nashik_slabs(db: Session) -> None:
    existing = incentive_repository.list_slabs(db, division="nashik")
    if existing:
        return
    samples = [
        {
            "division": "nashik",
            "slab_type": "MARGIN",
            "role": "RECRUITER",
            "margin_min": Decimal("10"),
            "margin_max": Decimal("20"),
            "hours_min": None,
            "hours_max": None,
            "amount": Decimal("5000"),
            "effective_from": date(2024, 1, 1),
            "is_active": True,
        },
        {
            "division": "nashik",
            "slab_type": "MARGIN",
            "role": "RECRUITER",
            "margin_min": Decimal("20"),
            "margin_max": Decimal("30"),
            "hours_min": None,
            "hours_max": None,
            "amount": Decimal("8000"),
            "effective_from": date(2024, 1, 1),
            "is_active": True,
        },
        {
            "division": "nashik",
            "slab_type": "HOURS",
            "role": "TEAM_LEAD",
            "margin_min": None,
            "margin_max": None,
            "hours_min": Decimal("160"),
            "hours_max": None,
            "amount": Decimal("3000"),
            "effective_from": date(2024, 1, 1),
            "is_active": True,
        },
    ]
    for data in samples:
        incentive_repository.create_slab(db, data)


def _seed_audit_logs(db: Session) -> None:
    if audit_repository.count_logs(db) > 0:
        return

    now = datetime.now(timezone.utc)
    samples = [
        {
            "action": AuditAction.FILE_UPLOAD,
            "title": "Uploaded Candidate New Start Data",
            "details": "Imported 48 active candidate records from New Start data Capture Feilds(in).csv",
            "user_display": "Accounts Department",
            "username": "rahul.pote",
            "metadata": {"fileName": "New Start data Capture Feilds(in).csv", "recordCount": 48},
            "created_at": now - timedelta(hours=5),
        },
        {
            "action": AuditAction.FILE_UPLOAD,
            "title": "Uploaded Project End Data",
            "details": "Loaded project completion schedule from Project End.xlsx for 12 candidates",
            "user_display": "Accounts Department",
            "username": "rahul.pote",
            "metadata": {"fileName": "Project End.xlsx", "recordCount": 12},
            "created_at": now - timedelta(hours=4),
        },
        {
            "action": AuditAction.FILE_UPLOAD,
            "title": "Uploaded Coordinator Dataset",
            "details": "Parsed June-Aug,2025 Ampcus.CSV. 4 recruiters auto-flagged as Auto-Filtered (Left).",
            "user_display": "Accounts Department",
            "username": "accounts_admin",
            "metadata": {"fileName": "June-Aug,2025 Ampcus.CSV", "totalRecruiters": 28, "leftCount": 4},
            "created_at": now - timedelta(hours=3),
        },
        {
            "action": AuditAction.HOURS_RECONCILIATION,
            "title": "Reconciled Hours against 160h Benchmark",
            "details": "Verified 44 candidates meeting 160h benchmark. 3 candidates flagged for Management Approval (>160h).",
            "user_display": "Accounts Department",
            "username": "rahul.pote",
            "metadata": {"totalCandidates": 47, "benchmarkHours": 160},
            "created_at": now - timedelta(hours=2),
        },
        {
            "action": AuditAction.CALCULATION_RUN,
            "title": "Ran Cycle Calculation",
            "details": "Calculated incentives for July 2026 cycle across US staffing division.",
            "user_display": "Accounts Department",
            "username": "rahul.pote",
            "metadata": {"month": "2026-07", "division": "US_STAFFING"},
            "created_at": now - timedelta(hours=1),
        },
    ]
    for entry in samples:
        audit_repository.write_log(db, **entry)
