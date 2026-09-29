from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user
from mis.db.session import get_db
from mis.models import ImportedJobDivaRecord, User
from mis.services.helpers import imported_to_start_response

router = APIRouter()


def _normalize_activity_id(activity_id: str) -> str:
    return activity_id.strip().lstrip("#")


@router.get("/records/{activity_id}")
async def get_jobdiva_record(
    activity_id: str,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    normalized = _normalize_activity_id(activity_id)
    numeric = normalized.upper().replace("JD-", "").replace("JD", "")

    result = await db.execute(
        select(ImportedJobDivaRecord).where(
            or_(
                func.lower(ImportedJobDivaRecord.activity_id) == normalized.lower(),
                ImportedJobDivaRecord.activity_id == numeric,
                ImportedJobDivaRecord.activity_id == f"JD-{numeric}",
            )
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Activity ID not found")
    return imported_to_start_response(record)

