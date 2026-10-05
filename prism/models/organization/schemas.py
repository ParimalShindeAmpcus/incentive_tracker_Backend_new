"""Organization Pydantic DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    is_active: bool
    created_at: Optional[datetime] = None


class DivisionCreate(BaseModel):
    name: str
    code: str
    organization_id: Optional[int] = 1
    description: Optional[str] = None
    calculation_engine: Optional[str] = "MARGIN_SLABS_PRO_RATA"
    is_active: bool = True
    seed_default_rules: bool = True


class DivisionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    calculation_engine: Optional[str] = None
    is_active: Optional[bool] = None


class DivisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    code: str
    name: str
    description: Optional[str] = None
    calculation_engine: Optional[str] = "MARGIN_SLABS_PRO_RATA"
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    rules_count: Optional[int] = 0
    active_rules_count: Optional[int] = 0

