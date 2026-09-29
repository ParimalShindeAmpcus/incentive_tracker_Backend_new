import re
from typing import Optional

from pydantic import EmailStr, Field, field_validator

from mis.schemas.common import CamelModel


class UserRead(CamelModel):
    id: int
    organization_id: int = Field(serialization_alias="organizationId")
    role_code: str = Field(serialization_alias="roleCode")
    employee_code: Optional[str] = Field(default=None, serialization_alias="employeeCode")
    full_name: str = Field(serialization_alias="fullName")
    email: EmailStr
    team_name: Optional[str] = Field(default=None, serialization_alias="teamName")
    phone: Optional[str] = None
    location: Optional[str] = None
    is_active: bool = Field(serialization_alias="isActive")
    is_super_admin: bool = Field(serialization_alias="isSuperAdmin")
    organization_name: Optional[str] = Field(default=None, serialization_alias="organizationName")
    manager_name: Optional[str] = Field(default=None, serialization_alias="managerName")
    role_display: Optional[str] = Field(default=None, serialization_alias="roleDisplay")


class UserListItem(CamelModel):
    id: str
    name: str
    email: str
    role: str
    team: str
    manager: str
    organization: str
    onboarding_organization: str = Field(default="", serialization_alias="onboardingOrganization")
    status: str


class UserCreate(CamelModel):
    full_name: str = Field(alias="fullName")
    email: EmailStr
    organization: str
    role: str
    team: str = ""
    manager_id: Optional[int] = Field(default=None, alias="managerId")
    manager_name: Optional[str] = Field(default=None, alias="managerName")
    onboarding_organization: Optional[str] = Field(default=None, alias="onboardingOrganization")
    password: Optional[str] = None
    is_active: bool = Field(default=True, alias="isActive")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if v is None:
            return v
        if not re.fullmatch(r"[^\W\d_]+(?:[ '-][^\W\d_]+)*", v, re.UNICODE):
            raise ValueError(
                "Full name can contain only letters, spaces, hyphens and apostrophes"
            )
        return v

    @field_validator("email")
    @classmethod
    def validate_strict_email(cls, v: str) -> str:
        if v and not re.match(r"^[0-9._-]*[a-zA-Z][a-zA-Z0-9._-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Email must contain at least one letter and no special characters")
        return v


class UserUpdate(CamelModel):
    full_name: Optional[str] = Field(default=None, alias="fullName")
    email: Optional[EmailStr] = None
    organization: Optional[str] = None
    role: Optional[str] = None
    team: Optional[str] = None
    manager_id: Optional[int] = Field(default=None, alias="managerId")
    manager_name: Optional[str] = Field(default=None, alias="managerName")
    onboarding_organization: Optional[str] = Field(default=None, alias="onboardingOrganization")
    is_active: Optional[bool] = Field(default=None, alias="isActive")
    password: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.fullmatch(r"[^\W\d_]+(?:[ '-][^\W\d_]+)*", v, re.UNICODE):
            raise ValueError(
                "Full name can contain only letters, spaces, hyphens and apostrophes"
            )
        return v

    @field_validator("email")
    @classmethod
    def validate_strict_email(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[0-9._-]*[a-zA-Z][a-zA-Z0-9._-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Email must contain at least one letter and no special characters")
        return v


class ResetPasswordRequest(CamelModel):
    password: str = Field(min_length=6)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str


class LoginResponse(CamelModel):
    access_token: str | None = Field(default=None, serialization_alias="accessToken")
    token_type: str = Field(default="bearer", serialization_alias="tokenType")
    role: str
    role_code: str = Field(serialization_alias="roleCode")
    name: str
    email: EmailStr
