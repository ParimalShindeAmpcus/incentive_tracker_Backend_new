from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io

from mis.api.v1.dependencies.auth import require_roles
from mis.core import rbac
from mis.db.session import get_db
from mis.models import User
from mis.services.analytics_service import incentive_summary

router = APIRouter()


@router.get("")
async def get_incentives(
    current_user: Annotated[User, Depends(require_roles(*rbac.AUTHENTICATED))],
    db: AsyncSession = Depends(get_db),
):
    return await incentive_summary(db, current_user)


@router.get("/export")
async def export_incentives(
    current_user: Annotated[User, Depends(require_roles(*rbac.ADMIN_ONLY))],
    db: AsyncSession = Depends(get_db),
):
    data = await incentive_summary(db, current_user)
    try:
        import pandas as pd

        buffer = io.BytesIO()
        pd.DataFrame(data["leaderboard"]).to_excel(buffer, index=False, sheet_name="Incentives")
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="incentive-report.xlsx"'},
        )
    except Exception as exc:
        raise exc


@router.post("/calculate")
async def calculate_incentives(
    current_user: Annotated[User, Depends(require_roles(*rbac.ADMIN_ONLY))],
    db: AsyncSession = Depends(get_db),
):
    data = await incentive_summary(db, current_user)
    return {
        "message": "Incentives recalculated from approved starts",
        "monthlyPayout": data["monthlyPayout"],
        "recruiterCount": len(data["leaderboard"]),
    }
