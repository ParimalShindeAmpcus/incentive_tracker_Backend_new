"""Pydantic DTOs for candidate_start — mirrored by MIS-web/src/types + schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SubmissionStatus(str, Enum):
    IMPORTED = "IMPORTED"
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    MANAGER_REVIEW = "MANAGER_REVIEW"
    MIS_REVIEW = "MIS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class CandidateStartBase(BaseModel):
    activity_id: str
    organization_id: int
    recruiter_id: int
    mapped_manager_id: Optional[int] = None
    submission_manager_id: Optional[int] = None

    candidate_name: Optional[str] = None
    candidate_email: Optional[EmailStr] = None
    candidate_contact_no: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    client_name: Optional[str] = None
    end_client_name: Optional[str] = None
    contract_type: Optional[str] = None
    sub_contractor_company: Optional[str] = None
    sub_contractor_email: Optional[EmailStr] = None
    sub_contractor_contact: Optional[str] = None
    req_id: Optional[str] = None
    job_title: Optional[str] = None
    job_level: Optional[str] = None
    salary: Optional[Decimal] = None
    pay_rate: Optional[Decimal] = None
    taxes: Optional[Decimal] = None
    benefits: Optional[Decimal] = None
    referral_fee: Optional[Decimal] = None
    gross_bill_rate: Optional[Decimal] = None
    msp_fee: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    margin_is_overridden: bool = False
    remote_position: Optional[bool] = None
    work_location: Optional[str] = None
    candidate_location: Optional[str] = None
    work_authorization: Optional[str] = None
    resume_source: Optional[str] = None

    team_lead: Optional[str] = None
    crm: Optional[str] = None
    team_manager: Optional[str] = None
    senior_manager: Optional[str] = None
    associate_director: Optional[str] = None
    director: Optional[str] = None
    center_head: Optional[str] = None
    assistant_vice_president: Optional[str] = None
    onboarding_coordinator: Optional[str] = None

    user_email: Optional[EmailStr] = None
    recruiter_location: Optional[str] = None
    status: SubmissionStatus = SubmissionStatus.DRAFT

    import re

    @field_validator("end_client_name")
    @classmethod
    def validate_end_client(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.fullmatch(r"[a-zA-Z0-9\s]*", v):
            raise ValueError("End client name must be alphanumeric")
        return v

class CandidateStartCreate(CandidateStartBase):
    imported_record_id: int


class CandidateStartUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_type: Optional[str] = None
    sub_contractor_company: Optional[str] = None
    sub_contractor_email: Optional[EmailStr] = None
    sub_contractor_contact: Optional[str] = None

    import re

    @field_validator("sub_contractor_company")
    @classmethod
    def validate_company(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.fullmatch(r"[^\W\d_]+(?:[ \-'.&][^\W\d_]+)*", v, re.UNICODE):
            raise ValueError("Company name must contain only letters and valid special characters")
        return v

    @field_validator("sub_contractor_email")
    @classmethod
    def validate_strict_email(cls, v: Optional[str]) -> Optional[str]:
        if v:
            import re
            if not re.match(r"^[0-9._-]*[a-zA-Z][a-zA-Z0-9._-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
                raise ValueError("Email must contain at least one letter and no special characters")
        return v

    job_level: Optional[str] = None
    salary: Optional[Decimal] = None
    pay_rate: Optional[Decimal] = None
    taxes: Optional[Decimal] = None
    benefits: Optional[Decimal] = None
    referral_fee: Optional[Decimal] = None
    gross_bill_rate: Optional[Decimal] = None
    msp_fee: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    margin_is_overridden: Optional[bool] = None
    remote_position: Optional[bool] = None
    resume_source: Optional[str] = None
    team_lead: Optional[str] = None
    crm: Optional[str] = None
    team_manager: Optional[str] = None
    senior_manager: Optional[str] = None
    associate_director: Optional[str] = None
    director: Optional[str] = None
    center_head: Optional[str] = None
    assistant_vice_president: Optional[str] = None
    onboarding_coordinator: Optional[str] = None
    recruiter_location: Optional[str] = None
    submission_manager_id: Optional[int] = None
    status: Optional[SubmissionStatus] = None
    version: Optional[int] = Field(default=None, description="Optimistic lock version")


class CandidateStartRead(CandidateStartBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    imported_record_id: int
    version: int
    created_at: datetime
    updated_at: datetime
