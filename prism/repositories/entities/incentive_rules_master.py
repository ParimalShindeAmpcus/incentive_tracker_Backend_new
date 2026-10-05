"""SQLAlchemy ORM entity for the Incentive Rules Master table."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from prism.core.db import Base


class IncentiveRuleMaster(Base):
    """Database-driven incentive rule configuration.

    Replaces hardcoded constants in nashik_rules.py, nashik_calculator.py,
    sambhaji_nagar.py, nashik_fte.py, ampcus_client.py, and ampcus_inhouse.py.

    rule_category values:
      RECRUITER_SLAB      — Nashik/SN margin-based recruiter slab
      LEADERSHIP_ONE_TIME — Nashik/SN W2/C2C leadership fixed amounts
      TEAM_LEAD           — Nashik team-lead base (per 160h)
      LOW_MARGIN          — Nashik low-margin special one-time
      PROJECT_END         — Nashik project-end special rule
      FTE_RECRUITER_SLAB  — FTE recruiter slab (placement count + finder fee)
      FTE_LEADERSHIP      — FTE leadership fixed amounts
      MARKUP_SLAB         — Ampcus Tech Client markup-% slab (per-role JSON)
      INHOUSE_AMOUNTS     — Ampcus Inhouse flat amounts
      GLOBAL_CONFIG       — Scalar config values (standard_hours, thresholds, etc.)
    """

    __tablename__ = "incentive_rule_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Scope
    division: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="nashik | sambhajiNagar | ampcusTechClient | ampcusTechInhouse",
    )
    rule_category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="RECRUITER_SLAB | LEADERSHIP_ONE_TIME | TEAM_LEAD | LOW_MARGIN | "
                "PROJECT_END | FTE_RECRUITER_SLAB | FTE_LEADERSHIP | MARKUP_SLAB | "
                "INHOUSE_AMOUNTS | GLOBAL_CONFIG",
    )

    # Role (NULL for non-role rules like GLOBAL_CONFIG)
    role: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Recruiter | Team Lead | Manager | Senior Manager | CRM | "
                "Associate Director | Center Head | AVP | Director",
    )

    # Named key (used for GLOBAL_CONFIG and INHOUSE_AMOUNTS rows)
    rule_key: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="e.g. standard_hours | max_roles_per_person | low_margin_threshold | "
                "team_lead_base | project_end_recruiter_amount | min_start_date | min_days",
    )

    # Slab bounds — margin-per-hour (USD)
    margin_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    margin_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))

    # Slab bounds — hours worked
    hours_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    hours_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))

    # Slab bounds — markup percentage (Ampcus Client)
    markup_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    markup_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))

    # FTE placement count slab bounds
    placement_count_min: Mapped[Optional[int]] = mapped_column(Integer)
    placement_count_max: Mapped[Optional[int]] = mapped_column(Integer)

    # FTE finder-fee classification (True = Above threshold, False = Below, NULL = N/A)
    finder_fee_above: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        comment="For FTE_RECRUITER_SLAB: True=above threshold, False=below, NULL=N/A",
    )

    # Primary INR amount (for slabs and fixed amounts)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))

    # Generic config value — JSON string for multi-role markup slabs, or scalar text
    config_value: Mapped[Optional[str]] = mapped_column(
        String(2000),
        comment="JSON string (for MARKUP_SLAB per-role amounts) or plain scalar text",
    )

    # Human-readable description
    description: Mapped[Optional[str]] = mapped_column(String(500))

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    effective_from: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    effective_to: Mapped[Optional[date]] = mapped_column(Date)

    # Audit
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
