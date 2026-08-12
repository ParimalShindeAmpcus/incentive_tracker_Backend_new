from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.repositories.entities.coordinator import CoordinatorStatus

class CoordinatorInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    organization: str = Field(min_length=1, max_length=255)
    role_title: str = Field(min_length=1, max_length=255)
    employment_status: CoordinatorStatus = CoordinatorStatus.ACTIVE
    start_date: Optional[date] = None
    exit_date: Optional[date] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None

class CoordinatorUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    organization: Optional[str] = None
    role_title: Optional[str] = None
    employment_status: Optional[CoordinatorStatus] = None
    start_date: Optional[date] = None
    exit_date: Optional[date] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None

class CoordinatorStatusUpdate(BaseModel):
    employment_status: CoordinatorStatus
    exit_date: Optional[date] = None

class CoordinatorListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; full_name: str; normalized_name: str; email: EmailStr; organization: str; role_title: str
    employment_status: CoordinatorStatus; start_date: Optional[date]; exit_date: Optional[date]; incentive_eligible: bool
    created_at: Optional[datetime] = None; updated_at: Optional[datetime] = None

class CoordinatorOut(CoordinatorListItem):
    bank_name: Optional[str] = None; account_number: Optional[str] = None; ifsc_code: Optional[str] = None

class CoordinatorPage(BaseModel):
    items: List[CoordinatorListItem]; total: int; page: int; page_size: int

class CoordinatorSummary(BaseModel):
    total_coordinators: int; active_coordinators: int; left_coordinators: int; notice_period_coordinators: int; incentive_eligible_coordinators: int

class UploadIssue(BaseModel):
    source_row: int; identifier: str; reason: str

class BulkUploadResponse(BaseModel):
    created_count: int; issues: List[UploadIssue]

class BulkMarkLeftResponse(BaseModel):
    marked_left_count: int; issues: List[UploadIssue]
