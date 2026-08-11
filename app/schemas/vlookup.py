from typing import List, Optional

from pydantic import BaseModel, Field


class VLookupRowIn(BaseModel):
    source_row_ref: Optional[str] = None
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    client: Optional[str] = None
    hours: Optional[float] = None


class VLookupMatchRequest(BaseModel):
    division: Optional[str] = None
    rows: List[VLookupRowIn] = Field(default_factory=list)


class VLookupMatchResult(BaseModel):
    source_row_ref: Optional[str] = None
    source_candidate_id: Optional[str] = None
    source_candidate_name: Optional[str] = None
    source_client: Optional[str] = None
    matched_candidate_id: Optional[int] = None
    matched_external_id: Optional[str] = None
    matched_name: Optional[str] = None
    match_method: str
    match_result: str
    confidence: str


class VLookupMatchResponse(BaseModel):
    total: int
    matched: int
    unmatched: int
    low_confidence: int
    results: List[VLookupMatchResult]
