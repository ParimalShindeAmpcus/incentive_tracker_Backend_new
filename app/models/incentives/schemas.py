"""Incentive Pydantic DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IncentiveLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cycle_id: int
    candidate_id: Optional[int] = None
    candidate_name: Optional[str] = None
    role: str
    person: str
    incentive_type: str
    rule_applied: Optional[str] = None
    eligible: bool
    base_incentive: Decimal
    pro_rata_factor: Decimal
    amount: Decimal
    hours: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    reason: Optional[str] = None
    explanation_json: Optional[str] = None
    payment_status: str
    created_at: Optional[datetime] = None


class IncentiveSlabOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    division: str
    slab_type: str
    role: str
    margin_min: Optional[Decimal] = None
    margin_max: Optional[Decimal] = None
    hours_min: Optional[Decimal] = None
    hours_max: Optional[Decimal] = None
    amount: Decimal
    effective_from: date
    effective_to: Optional[date] = None
    is_active: bool
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
