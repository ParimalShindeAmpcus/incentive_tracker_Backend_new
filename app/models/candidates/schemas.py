"""Candidate Pydantic DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_candidate_id: str
    activity_id: Optional[str] = None
    start_id: Optional[str] = None
    candidate_name: str
    normalized_name: str
    email: Optional[str] = None
    contact: Optional[str] = None
    client: Optional[str] = None
    end_client: Optional[str] = None
    job_title: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_project_ended: Optional[bool] = None
    req_id: Optional[str] = None
    contract_type: Optional[str] = None
    subcontractor: Optional[str] = None
    subcontractor_email: Optional[str] = None
    subcontractor_contact: Optional[str] = None
    job_level: Optional[str] = None
    salary: Optional[Decimal] = None
    pay_rate: Optional[Decimal] = None
    taxes: Optional[Decimal] = None
    benefits: Optional[Decimal] = None
    referral_fee: Optional[Decimal] = None
    finders_fee: Optional[Decimal] = None
    bill_rate: Optional[Decimal] = None
    msp_fee: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    markup_percent: Optional[Decimal] = None
    remote: Optional[str] = None
    work_location: Optional[str] = None
    candidate_location: Optional[str] = None
    work_authorization: Optional[str] = None
    candidate_source: Optional[str] = None
    team_lead: Optional[str] = None
    crm: Optional[str] = None
    manager: Optional[str] = None
    head_of_department: Optional[str] = None
    senior_manager: Optional[str] = None
    associate_director: Optional[str] = None
    director: Optional[str] = None
    center_head: Optional[str] = None
    avp: Optional[str] = None
    onboarding_coordinator: Optional[str] = None
    organization: Optional[str] = None
    user_email: Optional[str] = None
    recruiter_location: Optional[str] = None
    recruiter: Optional[str] = None
    status: Optional[str] = None
    placement_level: Optional[str] = None
    division: Optional[str] = None
    source_version_id: int
    last_touched_version_id: int
    is_active: bool
    incentive_active: bool
    inactivation_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CandidateUpdate(BaseModel):
    activity_id: Optional[str] = None
    start_id: Optional[str] = None
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    contact: Optional[str] = None
    client: Optional[str] = None
    end_client: Optional[str] = None
    job_title: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    req_id: Optional[str] = None
    contract_type: Optional[str] = None
    subcontractor: Optional[str] = None
    subcontractor_email: Optional[str] = None
    subcontractor_contact: Optional[str] = None
    job_level: Optional[str] = None
    salary: Optional[Decimal] = None
    pay_rate: Optional[Decimal] = None
    taxes: Optional[Decimal] = None
    benefits: Optional[Decimal] = None
    referral_fee: Optional[Decimal] = None
    finders_fee: Optional[Decimal] = None
    bill_rate: Optional[Decimal] = None
    msp_fee: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    remote: Optional[str] = None
    work_location: Optional[str] = None
    candidate_location: Optional[str] = None
    work_authorization: Optional[str] = None
    candidate_source: Optional[str] = None
    team_lead: Optional[str] = None
    crm: Optional[str] = None
    manager: Optional[str] = None
    head_of_department: Optional[str] = None
    senior_manager: Optional[str] = None
    associate_director: Optional[str] = None
    director: Optional[str] = None
    center_head: Optional[str] = None
    avp: Optional[str] = None
    onboarding_coordinator: Optional[str] = None
    organization: Optional[str] = None
    user_email: Optional[str] = None
    recruiter_location: Optional[str] = None
    recruiter: Optional[str] = None
    status: Optional[str] = None
    division: Optional[str] = None
    is_active: Optional[bool] = None
    incentive_active: Optional[bool] = None
    inactivation_reason: Optional[str] = None


class CandidateVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class CandidateRowIn(BaseModel):
    external_candidate_id: str
    activity_id: Optional[str] = None
    start_id: Optional[str] = None
    candidate_name: str
    email: Optional[str] = None
    contact: Optional[str] = None
    client: Optional[str] = None
    end_client: Optional[str] = None
    job_title: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    req_id: Optional[str] = None
    contract_type: Optional[str] = None
    subcontractor: Optional[str] = None
    subcontractor_email: Optional[str] = None
    subcontractor_contact: Optional[str] = None
    job_level: Optional[str] = None
    salary: Optional[Decimal] = None
    pay_rate: Optional[Decimal] = None
    taxes: Optional[Decimal] = None
    benefits: Optional[Decimal] = None
    referral_fee: Optional[Decimal] = None
    finders_fee: Optional[Decimal] = None
    bill_rate: Optional[Decimal] = None
    gross_bill_rate: Optional[Decimal] = None
    msp_fee: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    remote: Optional[str] = None
    work_location: Optional[str] = None
    candidate_location: Optional[str] = None
    work_authorization: Optional[str] = None
    candidate_source: Optional[str] = None
    resume_source: Optional[str] = None
    team_lead: Optional[str] = None
    crm: Optional[str] = None
    manager: Optional[str] = None
    head_of_department: Optional[str] = None
    senior_manager: Optional[str] = None
    associate_director: Optional[str] = None
    director: Optional[str] = None
    center_head: Optional[str] = None
    avp: Optional[str] = None
    onboarding_coordinator: Optional[str] = None
    organization: Optional[str] = None
    user_email: Optional[str] = None
    recruiter_location: Optional[str] = None
    recruiter: Optional[str] = None
    status: Optional[str] = None
    placement_level: Optional[str] = None
    division: Optional[str] = None


class CreateVersionRequest(BaseModel):
    version_label: str
    division: Optional[str] = None
    source_filename: Optional[str] = None
    notes: Optional[str] = None
    rows: List[CandidateRowIn] = Field(default_factory=list)


class CandidateVersionCreateResponse(BaseModel):
    version: CandidateVersionOut
    created_count: int


class PaginatedCandidates(BaseModel):
    items: List[CandidateOut]
    total: int
    page: int
    page_size: int
