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


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    division_id: Optional[int] = None
    employee_code: Optional[str] = None
    full_name: str
    normalized_name: str
    email: Optional[str] = None
    role_title: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
