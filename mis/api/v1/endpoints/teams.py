from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mis.core.deps import get_current_user, require_roles
from mis.db.session import get_db
from mis.models import RecruiterManagerMapping, Role, User
from mis.services.analytics_service import recruiter_leaderboard

router = APIRouter()


class TeamCreateBody(BaseModel):
    name: str = Field(min_length=1)
    manager_name: str = Field(alias="managerName")
    recruiter_name: str | None = Field(default=None, alias="recruiterName")

    model_config = {"populate_by_name": True}


@router.get("")
async def get_teams(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            User.team_name,
            func.count(User.id).label("members"),
            func.coalesce(func.sum(0), 0),
        )
        .join(Role, Role.id == User.role_id)
        .where(
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            User.team_name.is_not(None),
            User.team_name != "",
        )
        .group_by(User.team_name)
        .order_by(User.team_name)
    )
    if current_user.role and current_user.role.code == "MANAGER":
        stmt = stmt.where(
            User.id.in_(
                select(RecruiterManagerMapping.recruiter_id).where(
                    RecruiterManagerMapping.manager_id == current_user.id,
                    RecruiterManagerMapping.is_active.is_(True),
                )
            )
            | (User.id == current_user.id)
        )

    team_rows = (await db.execute(stmt)).all()
    leaderboard = await recruiter_leaderboard(db, current_user)

    margin_by_team: dict[str, float] = {}
    for entry in leaderboard:
        user = (
            await db.execute(
                select(User)
                .where(
                    func.lower(User.full_name) == entry["name"].lower(),
                    User.deleted_at.is_(None),
                )
                .order_by(User.is_active.desc(), User.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if user and user.team_name:
            margin_by_team[user.team_name] = margin_by_team.get(user.team_name, 0) + entry["margin"]

    teams = []
    for row in team_rows:
        team_name = row.team_name
        manager = (
            await db.execute(
                select(User)
                .join(Role, Role.id == User.role_id)
                .where(
                    User.team_name == team_name,
                    Role.code.in_(("MANAGER", "TEAM_LEAD")),
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        margin = margin_by_team.get(team_name, 0)
        target = 75_000 * max(int(row.members or 1), 1)
        teams.append(
            {
                "id": team_name,
                "name": team_name,
                "manager": manager.full_name if manager else "Unassigned",
                "members": int(row.members or 0),
                "margin": margin,
                "target": min(100, round((margin / target) * 100)) if target else 0,
            }
        )
    return teams


@router.get("/{team_id}")
async def get_team(
    team_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    members = (
        await db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.team_name == team_id, User.deleted_at.is_(None), User.is_active.is_(True))
        )
    ).scalars().all()
    if not members:
        raise HTTPException(status_code=404, detail="Team not found")
    return {
        "id": team_id,
        "name": team_id,
        "members": [
            {
                "id": str(m.id),
                "name": m.full_name,
                "email": m.email,
                "role": m.role.code if m.role else "",
            }
            for m in members
        ],
    }


@router.post("")
async def create_team(
    body: TeamCreateBody,
    current_user: Annotated[User, Depends(require_roles("MIS"))],
    db: AsyncSession = Depends(get_db),
):
    team_name = body.name.strip()
    manager = (
        await db.execute(
            select(User)
            .join(Role, Role.id == User.role_id)
            .where(
                func.lower(User.full_name) == body.manager_name.strip().lower(),
                User.deleted_at.is_(None),
            )
            .order_by(User.is_active.desc(), User.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    manager.team_name = team_name
    if body.recruiter_name:
        recruiter = (
            await db.execute(
                select(User)
                .where(
                    func.lower(User.full_name) == body.recruiter_name.strip().lower(),
                    User.deleted_at.is_(None),
                )
                .order_by(User.is_active.desc(), User.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if recruiter:
            recruiter.team_name = team_name
            mapping = (
                await db.execute(
                    select(RecruiterManagerMapping).where(
                        RecruiterManagerMapping.recruiter_id == recruiter.id,
                        RecruiterManagerMapping.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if mapping:
                mapping.manager_id = manager.id
            else:
                db.add(
                    RecruiterManagerMapping(
                        recruiter_id=recruiter.id,
                        manager_id=manager.id,
                        organization_id=recruiter.organization_id,
                        created_by=current_user.id,
                    )
                )

    await db.commit()
    return {"message": f"Team {team_name} created", "name": team_name, "manager": manager.full_name}
