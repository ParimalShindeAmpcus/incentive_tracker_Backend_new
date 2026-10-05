"""Incentive Rules Master — Pydantic DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Allowed enum values (for documentation and basic validation)
# ---------------------------------------------------------------------------

VALID_DIVISIONS = {
    "nashik",
    "sambhajiNagar",
    "ampcusTechClient",
    "ampcusTechInhouse",
}

VALID_CATEGORIES = {
    "RECRUITER_SLAB",
    "LEADERSHIP_ONE_TIME",
    "TEAM_LEAD",
    "LOW_MARGIN",
    "PROJECT_END",
    "FTE_RECRUITER_SLAB",
    "FTE_LEADERSHIP",
    "MARKUP_SLAB",
    "INHOUSE_AMOUNTS",
    "GLOBAL_CONFIG",
}

VALID_ROLES = {
    "Recruiter",
    "Team Lead",
    "Manager",
    "Senior Manager",
    "CRM",
    "Associate Director",
    "Center Head",
    "AVP",
    "Director",
    "CH/VP",
}


# ---------------------------------------------------------------------------
# Input schema (create / update)
# ---------------------------------------------------------------------------


class IncentiveRuleMasterIn(BaseModel):
    division: str = Field(..., description="nashik | sambhajiNagar | ampcusTechClient | ampcusTechInhouse")
    rule_category: str = Field(..., description="RECRUITER_SLAB | LEADERSHIP_ONE_TIME | ...")
    role: Optional[str] = Field(None, description="Recruiter | Team Lead | ...")
    rule_key: Optional[str] = Field(None, description="e.g. standard_hours, low_margin_threshold")

    # Slab bounds
    margin_min: Optional[Decimal] = None
    margin_max: Optional[Decimal] = None
    hours_min: Optional[Decimal] = None
    hours_max: Optional[Decimal] = None
    markup_min: Optional[Decimal] = None
    markup_max: Optional[Decimal] = None
    placement_count_min: Optional[int] = None
    placement_count_max: Optional[int] = None
    finder_fee_above: Optional[bool] = None

    # Values
    amount: Optional[Decimal] = None
    config_value: Optional[str] = None
    description: Optional[str] = None

    # Lifecycle
    is_active: bool = True
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None

    @field_validator("division")
    @classmethod
    def validate_division(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("division cannot be empty")
        return v.strip()

    @field_validator("rule_category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("rule_category cannot be empty")
        return v.strip()


class IncentiveRuleMasterUpdate(BaseModel):
    """Partial update — all fields optional."""

    division: Optional[str] = None
    rule_category: Optional[str] = None
    role: Optional[str] = None
    rule_key: Optional[str] = None
    margin_min: Optional[Decimal] = None
    margin_max: Optional[Decimal] = None
    hours_min: Optional[Decimal] = None
    hours_max: Optional[Decimal] = None
    markup_min: Optional[Decimal] = None
    markup_max: Optional[Decimal] = None
    placement_count_min: Optional[int] = None
    placement_count_max: Optional[int] = None
    finder_fee_above: Optional[bool] = None
    amount: Optional[Decimal] = None
    config_value: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


# ---------------------------------------------------------------------------
# Output schema (API responses)
# ---------------------------------------------------------------------------


class IncentiveRuleMasterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    division: str
    rule_category: str
    role: Optional[str] = None
    rule_key: Optional[str] = None

    margin_min: Optional[Decimal] = None
    margin_max: Optional[Decimal] = None
    hours_min: Optional[Decimal] = None
    hours_max: Optional[Decimal] = None
    markup_min: Optional[Decimal] = None
    markup_max: Optional[Decimal] = None
    placement_count_min: Optional[int] = None
    placement_count_max: Optional[int] = None
    finder_fee_above: Optional[bool] = None

    amount: Optional[Decimal] = None
    config_value: Optional[str] = None
    description: Optional[str] = None

    is_active: bool
    effective_from: date
    effective_to: Optional[date] = None

    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
