"""VLookup service stubs."""

from app.models.vlookup.schemas import (
    VLookupMatchItem,
    VLookupMatchRequest,
    VLookupMatchResponse,
    VLookupTemplateResponse,
)


def match(payload: VLookupMatchRequest) -> VLookupMatchResponse:
    items = [
        VLookupMatchItem(input_name=name, matched_name=None, confidence=None, method=None)
        for name in payload.names
    ]
    return VLookupMatchResponse(matches=items)


def template() -> VLookupTemplateResponse:
    return VLookupTemplateResponse()
