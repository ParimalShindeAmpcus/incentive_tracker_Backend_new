"""Special Incentive (Recruiter of the Month) response DTOs."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SpecialIncentiveCandidateOut(BaseModel):
    candidate_id: Optional[str] = None
    start_id: Optional[str] = None
    candidate_name: str
    recruiter: Optional[str] = None
    organization: Optional[str] = None
    client: Optional[str] = None
    start_date: Optional[str] = None
    c3_margin: Optional[float] = None
    contract_type: Optional[str] = None


class PlacementWinnerOut(BaseModel):
    recruiter: str
    placement_count: int
    incentive: float
    candidates: List[SpecialIncentiveCandidateOut] = Field(default_factory=list)


class HighestPlacementsAwardOut(BaseModel):
    category: str = "highest_placements"
    label: str = "Highest Placements"
    is_tie: bool = False
    incentive_per_award: float = 5000
    winners: List[PlacementWinnerOut] = Field(default_factory=list)
    message: Optional[str] = None


class MarginWinnerOut(BaseModel):
    recruiter: str
    candidate_name: str
    candidate_id: Optional[str] = None
    start_id: Optional[str] = None
    start_date: Optional[str] = None
    c3_margin: float
    incentive: float
    candidate_count: int = 1
    candidate: SpecialIncentiveCandidateOut
    candidates: List[SpecialIncentiveCandidateOut] = Field(default_factory=list)


class HighestMarginAwardOut(BaseModel):
    category: str = "highest_margin"
    label: str = "Highest Margin"
    is_tie: bool = False
    incentive_per_award: float = 5000
    winners: List[MarginWinnerOut] = Field(default_factory=list)
    message: Optional[str] = None


class OrganizationAwardsOut(BaseModel):
    key: str
    name: str
    highest_placements: HighestPlacementsAwardOut
    highest_margin: HighestMarginAwardOut
    eligible_candidate_count: int = 0


class SpecialIncentiveTotalsOut(BaseModel):
    possible_awards: int = 4
    possible_amount: float = 20000
    awarded_count: int = 0
    awarded_amount: float = 0


class SpecialIncentiveResponse(BaseModel):
    month: str
    month_label: str
    incentive_amount: float = 5000
    tie_pay_all: bool = True
    organizations: List[OrganizationAwardsOut] = Field(default_factory=list)
    totals: SpecialIncentiveTotalsOut = Field(default_factory=SpecialIncentiveTotalsOut)
    source: str = "candidate_master"


class SpecialIncentiveDetailsResponse(BaseModel):
    month: str
    organization: str
    category: str
    recruiter: Optional[str] = None
    is_tie: bool = False
    incentive_per_award: float = 5000
    placement_count: Optional[int] = None
    c3_margin: Optional[float] = None
    candidates: List[SpecialIncentiveCandidateOut] = Field(default_factory=list)
    message: Optional[str] = None
