"""VLookup stub DTOs."""

from typing import List, Optional

from pydantic import BaseModel, Field


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
    message: str = "stub — matching engine not implemented"


class VLookupTemplateResponse(BaseModel):
    columns: List[str] = Field(default_factory=lambda: ["candidate_name", "client", "hours"])
    message: str = "stub template"
