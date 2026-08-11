"""VLookup HTTP routes (stubs)."""

from fastapi import APIRouter

from app.models.vlookup.schemas import VLookupMatchRequest, VLookupMatchResponse, VLookupTemplateResponse
from app.services.vlookup import vlookup_service

router = APIRouter()


@router.post("/match", response_model=VLookupMatchResponse)
def match(payload: VLookupMatchRequest) -> VLookupMatchResponse:
    return vlookup_service.match(payload)


@router.get("/template", response_model=VLookupTemplateResponse)
def template() -> VLookupTemplateResponse:
    return vlookup_service.template()
