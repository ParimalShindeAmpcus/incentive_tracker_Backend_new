from typing import Optional

from mis.schemas.common import CamelModel


class ImportedStartResponse(CamelModel):
    activity_id: str
    candidate_name: str
    candidate_email: str
    candidate_contact: str
    start_date: str
    end_date: str
    client_name: str
    end_client_name: str
    req_id: str
    job_title: str
    work_location: str
    candidate_location: str
    work_authorization: str
    recruiter_name: str


class DropdownItemRead(CamelModel):
    id: Optional[int] = None
    category: str
    value: str
    display_order: Optional[int] = None
    is_active: Optional[bool] = True
    organization_id: Optional[int] = None


class SubcontractorRead(CamelModel):
    id: Optional[int] = None
    name: str
    email: str = ""
    phone: str = ""
    is_active: Optional[bool] = True


class PaginatedStarts(CamelModel):
    items: list
    total: int
    page: int
    page_size: int
