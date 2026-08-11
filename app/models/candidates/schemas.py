"""Candidate Pydantic DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_candidate_id: str
    start_id: Optional[str] = None
    candidate_name: str
    normalized_name: str
    email: Optional[str] = None
    client: Optional[str] = None
    end_client: Optional[str] = None
    contract_type: Optional[str] = None
    pay_rate: Optional[Decimal] = None
    bill_rate: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    markup_percent: Optional[Decimal] = None
    finders_fee: Optional[Decimal] = None
    start_date: Optional[date] = None
    recruiter: Optional[str] = None
    team_lead: Optional[str] = None
    manager: Optional[str] = None
    senior_manager: Optional[str] = None
    crm: Optional[str] = None
    associate_director: Optional[str] = None
    center_head: Optional[str] = None
    avp: Optional[str] = None
    onboarding_coordinator: Optional[str] = None
    organization: Optional[str] = None
    candidate_source: Optional[str] = None
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
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    client: Optional[str] = None
    end_client: Optional[str] = None
    contract_type: Optional[str] = None
    pay_rate: Optional[Decimal] = None
    bill_rate: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    status: Optional[str] = None
    division: Optional[str] = None
    recruiter: Optional[str] = None
    team_lead: Optional[str] = None
    manager: Optional[str] = None
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
    candidate_name: str
    email: Optional[str] = None
    client: Optional[str] = None
    division: Optional[str] = None
    start_id: Optional[str] = None
    status: Optional[str] = None
    recruiter: Optional[str] = None
    pay_rate: Optional[Decimal] = None
    bill_rate: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    start_date: Optional[date] = None


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
