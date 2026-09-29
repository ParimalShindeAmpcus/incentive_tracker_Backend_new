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


class DivisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    code: str
    name: str
    is_active: bool
    created_at: Optional[datetime] = None
