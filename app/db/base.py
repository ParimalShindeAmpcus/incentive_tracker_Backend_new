from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic / metadata see them
from app.models import (  # noqa: E402,F401
    audit,
    candidate,
    cycle,
    hours,
    incentive_line,
    incentive_slab,
    organization,
    paid_ledger,
    project_end,
    recruiter,
    user,
)
