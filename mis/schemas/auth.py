from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from mis.schemas.common import CamelModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role_code: str
    role_label: str
    organization_id: int
    organization_name: str | None = None
    team_name: str | None = None
    phone: str | None = None
    location: str | None = None
    is_super_admin: bool = False
    is_active: bool = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(CamelModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)


class TokenValidationResponse(BaseModel):
    valid: bool


class InvitationAcceptRequest(CamelModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)


class ProfileUpdate(CamelModel):
    full_name: str | None = Field(default=None, alias="fullName")
    phone: str | None = None
    location: str | None = None


class ProfileRead(CamelModel):
    id: int
    email: EmailStr
    full_name: str = Field(serialization_alias="fullName")
    role_code: str = Field(serialization_alias="roleCode")
    role_label: str = Field(serialization_alias="roleLabel")
    organization_id: int = Field(serialization_alias="organizationId")
    organization_name: str | None = Field(default=None, serialization_alias="organizationName")
    team_name: str | None = Field(default=None, serialization_alias="teamName")
    phone: str | None = None
    location: str | None = None
    is_super_admin: bool = Field(default=False, serialization_alias="isSuperAdmin")
    is_active: bool = Field(default=True, serialization_alias="isActive")
