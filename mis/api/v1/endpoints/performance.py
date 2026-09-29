from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user
from mis.db.session import get_db
from mis.models import User
from mis.services.analytics_service import recruiter_leaderboard

router = APIRouter()


@router.get("")
async def get_performance(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    leaderboard = await recruiter_leaderboard(db, current_user)
    return {"leaderboard": leaderboard}
