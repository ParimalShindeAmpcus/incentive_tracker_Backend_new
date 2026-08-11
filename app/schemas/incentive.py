from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class IncentiveLineOut(BaseModel):
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
    payment_status: str

    model_config = {"from_attributes": True}


class IncentiveSlabOut(BaseModel):
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

    model_config = {"from_attributes": True}


class PaymentCreate(BaseModel):
    incentive_line_id: int
    payment_reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentOut(BaseModel):
    id: int
    incentive_line_id: int
    amount: Decimal
    payment_reference: Optional[str] = None
    status: str
    paid_at: datetime

    model_config = {"from_attributes": True}
