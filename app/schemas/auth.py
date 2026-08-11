from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RoleOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_active: bool
    roles: List[RoleOut] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
