"""Auth Pydantic DTOs."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(ch.isupper() for ch in value):
            raise ValueError("Password must include at least one uppercase character")
        if not any(ch.islower() for ch in value):
            raise ValueError("Password must include at least one lowercase character")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("Password must include at least one digit")
        if not any(not ch.isalnum() for ch in value):
            raise ValueError("Password must include at least one special character")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
    roles: List[RoleOut] = []
    created_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
