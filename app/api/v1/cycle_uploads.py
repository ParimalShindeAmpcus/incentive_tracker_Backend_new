"""Upload-adjacent cycle helpers (version binding).

Primary upload endpoints live under candidate-data / hours-data / project-end /
recruiter-master. This module exposes cycle-level version attachment.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.cycle import CycleOut, CycleUpdate
from app.services import cycle_service

router = APIRouter(prefix="/cycles", tags=["cycle-uploads"])


class BindVersionsRequest(BaseModel):
    candidate_version_id: Optional[int] = None
    recruiter_version_id: Optional[int] = None
    hours_version_id: Optional[int] = None
    project_end_version_id: Optional[int] = None


@router.post("/{cycle_id}/bind-versions", response_model=CycleOut)
def bind_versions(
    cycle_id: int,
    payload: BindVersionsRequest,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return cycle_service.update_cycle(
        db,
        cycle_id,
        user,
        CycleUpdate(**payload.model_dump(exclude_unset=True)),
    )
