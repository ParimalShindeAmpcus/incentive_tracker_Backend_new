from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.vlookup import VLookupMatchRequest, VLookupMatchResponse
from app.services import vlookup_service

router = APIRouter(prefix="/vlookup", tags=["vlookup"])


@router.get("/template")
def download_template(user: User = Depends(require_role("ADMIN", "ACCOUNTS", "VIEWER"))):
    data = vlookup_service.build_template_xlsx()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=vlookup_template.xlsx"},
    )


@router.post("/match", response_model=VLookupMatchResponse)
def match_rows(
    payload: VLookupMatchRequest,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return vlookup_service.match(db, payload)
