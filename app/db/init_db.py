from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.hours import HoursBenchmark
from app.models.incentive_slab import IncentiveSlab
from app.models.organization import Division, Employee, Organization
from app.models.user import Role, User
from app.repositories import user_repo

DEFAULT_ROLES = ("ADMIN", "ACCOUNTS", "VIEWER")

# Seed slabs from frontend incentiveRules (config-driven, not hardcoded in engine).
NASHIK_RECRUITER_SLABS = [
    (1.0, 2.0, 500),
    (2.01, 4.0, 1000),
    (4.01, 6.0, 1500),
    (6.01, 8.0, 2000),
    (8.01, 10.0, 2500),
    (10.01, 15.0, 3500),
    (15.01, 20.0, 4000),
    (20.01, 30.0, 4500),
    (30.01, 40.0, 7000),
    (40.01, 50.0, 10000),
]

NASHIK_LEADERSHIP = [
    ("CRM", 1000),
    ("Manager", 1500),
    ("Senior Manager", 1500),
    ("Associate Director", 1750),
    ("Center Head", 1500),
    ("AVP", 2300),
]


def seed_roles_and_admin(db: Session) -> None:
    settings = get_settings()
    for name in DEFAULT_ROLES:
        if not db.query(Role).filter(Role.name == name).first():
            db.add(Role(name=name, description=f"{name} role"))
    db.flush()

    admin = user_repo.get_by_email(db, settings.default_admin_email)
    if not admin:
        admin_role = db.query(Role).filter(Role.name == "ADMIN").one()
        accounts_role = db.query(Role).filter(Role.name == "ACCOUNTS").one()
        admin = User(
            email=settings.default_admin_email,
            full_name="System Admin",
            hashed_password=hash_password(settings.default_admin_password),
            is_active=True,
        )
        admin.roles = [admin_role, accounts_role]
        db.add(admin)


def seed_org_divisions(db: Session) -> None:
    org = db.query(Organization).filter(Organization.code == "DEFAULT").first()
    if not org:
        org = Organization(code="DEFAULT", name="Default Organization")
        db.add(org)
        db.flush()

    divisions = [
        ("nashik", "Nashik Division"),
        ("sambhajiNagar", "Sambhaji Nagar Division"),
        ("ampcusTechClient", "Ampcus Tech (Client)"),
        ("ampcusTechInhouse", "Ampcus Tech In-House"),
        ("fulltime", "Full-Time Placements"),
    ]
    for code, name in divisions:
        existing = db.query(Division).filter(Division.code == code).first()
        if not existing:
            db.add(Division(organization_id=org.id, code=code, name=name))


def seed_hours_benchmarks(db: Session) -> None:
    defaults = [
        ("nashik", 160),
        ("sambhajiNagar", 160),
        ("ampcusTechClient", 160),
        ("ampcusTechInhouse", 0),
        ("fulltime", 160),
    ]
    for division, hours in defaults:
        if not db.query(HoursBenchmark).filter(HoursBenchmark.division == division).first():
            db.add(
                HoursBenchmark(
                    division=division,
                    benchmark_hours=Decimal(str(hours)),
                    description=f"Default benchmark for {division}",
                    is_active=True,
                )
            )


def seed_incentive_slabs(db: Session) -> None:
    if db.query(IncentiveSlab).count() > 0:
        return
    today = date.today()
    for margin_min, margin_max, amount in NASHIK_RECRUITER_SLABS:
        db.add(
            IncentiveSlab(
                division="nashik",
                slab_type="MARGIN_RECURRING",
                role="Recruiter",
                margin_min=Decimal(str(margin_min)),
                margin_max=Decimal(str(margin_max)),
                hours_min=Decimal("0"),
                hours_max=None,
                amount=Decimal(str(amount)),
                effective_from=today,
                is_active=True,
            )
        )
    db.add(
        IncentiveSlab(
            division="nashik",
            slab_type="LOW_MARGIN_ONETIME",
            role="Recruiter",
            margin_min=Decimal("0"),
            margin_max=Decimal("0.99"),
            hours_min=Decimal("0"),
            hours_max=None,
            amount=Decimal("2000"),
            effective_from=today,
            is_active=True,
        )
    )
    db.add(
        IncentiveSlab(
            division="nashik",
            slab_type="TEAM_LEAD_RECURRING",
            role="Team Lead",
            margin_min=None,
            margin_max=None,
            hours_min=Decimal("0"),
            hours_max=None,
            amount=Decimal("250"),
            effective_from=today,
            is_active=True,
        )
    )
    for role, amount in NASHIK_LEADERSHIP:
        db.add(
            IncentiveSlab(
                division="nashik",
                slab_type="LEADERSHIP_ONETIME",
                role=role,
                margin_min=None,
                margin_max=None,
                hours_min=Decimal("160"),
                hours_max=None,
                amount=Decimal(str(amount)),
                effective_from=today,
                is_active=True,
            )
        )
    db.add(
        IncentiveSlab(
            division="nashik",
            slab_type="PROJECT_END_SPECIAL",
            role="Recruiter",
            margin_min=None,
            margin_max=None,
            hours_min=Decimal("0"),
            hours_max=Decimal("159.99"),
            amount=Decimal("2000"),
            effective_from=today,
            is_active=True,
        )
    )

    # Sambhaji margin x hours matrix (simplified seed rows)
    sambhaji_bands = [
        (1, 3, [500, 1000, 2000, 3000, 4000]),
        (3.01, 5, [1000, 2000, 3000, 4000, 5000]),
        (5.01, 7, [2000, 3000, 4000, 5000, 7000]),
        (7.01, 10, [3000, 4000, 5000, 6000, 8500]),
        (10.01, 15, [4000, 5000, 6000, 7000, 10000]),
        (15.01, 20, [5000, 6000, 7000, 8000, 15000]),
        (20.01, 30, [6000, 7000, 8000, 10000, 20000]),
        (30.01, 50, [7000, 8000, 9000, 12000, 25000]),
    ]
    hour_bands = [(0, 40), (41, 80), (81, 120), (121, 160), (161, 100000)]
    for mmin, mmax, amounts in sambhaji_bands:
        for (hmin, hmax), amount in zip(hour_bands, amounts):
            db.add(
                IncentiveSlab(
                    division="sambhajiNagar",
                    slab_type="MARGIN_HOURS_MATRIX",
                    role="Recruiter",
                    margin_min=Decimal(str(mmin)),
                    margin_max=Decimal(str(mmax)),
                    hours_min=Decimal(str(hmin)),
                    hours_max=Decimal(str(hmax)),
                    amount=Decimal(str(amount)),
                    effective_from=today,
                    is_active=True,
                )
            )


def init_db(db: Session) -> None:
    seed_roles_and_admin(db)
    seed_org_divisions(db)
    seed_hours_benchmarks(db)
    seed_incentive_slabs(db)
    db.commit()
