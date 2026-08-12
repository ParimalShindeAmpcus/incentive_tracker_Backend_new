"""VLOOKUP reconciliation API DTOs."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VLookupUploadResponse(BaseModel):
    status: str = "success"
    batch_id: str
    target_month: Optional[str] = None
    template_month: Optional[str] = None
    client_file_format: Optional[str] = None
    template_count: int = 0
    template_created: int = 0
    template_reused: int = 0
    messy_count: int = 0
    client_candidate_count: Optional[int] = None
    months_in_client_file: List[str] = Field(default_factory=list)
    matched_count: int = 0
    needs_review_count: int = 0
    unmatched_count: int = 0
    duplicate_count: int = 0
    conflicting_count: int = 0
    parser_warnings: List[str] = Field(default_factory=list)
    month_note: Optional[str] = None
    total_records: int = 0


class VLookupStatsResponse(BaseModel):
    batch_id: Optional[str] = None
    matched_count: int = 0
    needs_review_count: int = 0
    unmatched_count: int = 0
    duplicate_count: int = 0
    conflicting_count: int = 0
    total_records: int = 0
    target_month: Optional[str] = None
    client_file_format: Optional[str] = None
    parser_warnings: List[Any] = Field(default_factory=list)


class VLookupReviewBody(BaseModel):
    reviewed_by: Optional[str] = "accounts"
    notes: Optional[str] = None


class VLookupRematchBody(BaseModel):
    template_candidate_id: int = Field(..., description="Template candidate PK to link")
    reviewed_by: Optional[str] = "accounts"
    notes: Optional[str] = None
    accept: bool = True


class VLookupActionResponse(BaseModel):
    status: str = "success"
    match_id: int
    message: str
    template_candidate_id: Optional[str] = None
    template_candidate_name: Optional[str] = None


class VLookupMatchesByStatusResponse(BaseModel):
    status: str
    batch_id: Optional[str] = None
    matches: List[Dict[str, Any]] = Field(default_factory=list)


class VLookupTemplateCandidateOut(BaseModel):
    id: int
    candidate_id: str
    candidate_name: str
    client_name: Optional[str] = None
    month: Optional[str] = None
    why_suggested: str = ""
    identity_compatible: bool = False
    confidence: float = 0


class VLookupTemplateSearchResponse(BaseModel):
    candidates: List[VLookupTemplateCandidateOut] = Field(default_factory=list)


# Keep legacy stub schemas so any old clients don't break on import
class VLookupMatchRequest(BaseModel):
    names: List[str] = Field(default_factory=list)
    division: Optional[str] = None


class VLookupMatchItem(BaseModel):
    input_name: str
    matched_name: Optional[str] = None
    candidate_id: Optional[int] = None
    confidence: Optional[str] = None
    method: Optional[str] = None


class VLookupMatchResponse(BaseModel):
    matches: List[VLookupMatchItem] = Field(default_factory=list)
    message: str = "Use POST /vlookup/upload for hours reconciliation"


class VLookupTemplateResponse(BaseModel):
    columns: List[str] = Field(
        default_factory=lambda: [
            "Candidate ID",
            "Candidate Name",
            "Client Name",
            "Hours Worked",
            "Month",
        ]
    )
    message: str = "Upload Hours Template + client hours via POST /vlookup/upload"
