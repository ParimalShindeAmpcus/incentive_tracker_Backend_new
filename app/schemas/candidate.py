from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class CandidateOut(BaseModel):
    id: int
    external_candidate_id: str
    start_id: Optional[str] = None
    candidate_name: str
    client: Optional[str] = None
    contract_type: Optional[str] = None
    margin: Optional[Decimal] = None
    start_date: Optional[date] = None
    recruiter: Optional[str] = None
    team_lead: Optional[str] = None
    manager: Optional[str] = None
    senior_manager: Optional[str] = None
    crm: Optional[str] = None
    associate_director: Optional[str] = None
    center_head: Optional[str] = None
    avp: Optional[str] = None
    organization: Optional[str] = None
    candidate_source: Optional[str] = None
    status: Optional[str] = None
    division: Optional[str] = None
    source_version_id: int
    last_touched_version_id: int

    model_config = {"from_attributes": True}


class CandidateVersionOut(BaseModel):
    id: int
    version_label: str
    source_filename: Optional[str] = None
    division: Optional[str] = None
    row_count: int
    uploaded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    created_candidates: int = 0
    updated_candidates: int = 0

    model_config = {"from_attributes": True}


class CandidateVersionCreateResponse(BaseModel):
    version: CandidateVersionOut
    created_candidates: int
    updated_candidates: int
    duplicates_flagged: int
