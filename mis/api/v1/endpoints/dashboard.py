from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user
from mis.core.constants import (
    HOD_LIKE_ROLES,
    ONBOARD_ROLES,
    ONBOARD_REVIEWABLE_STATUSES,
    is_leadership_role,
)
from mis.db.session import get_db
from mis.models import CandidateStart, Organization, Role, User
from mis.services.start_scoping import build_start_visibility_conditions

router = APIRouter()

APPROVED_STATUSES = ("APPROVED", "COMPLETED")
PENDING_STATUSES = ("SUBMITTED", "MANAGER_REVIEW", "ONBOARDING_REVIEW", "MIS_REVIEW")


def _scope_starts(stmt, current_user: User):
    for cond in build_start_visibility_conditions(current_user):
        stmt = stmt.where(cond)
    if current_user.role and current_user.role.code in ONBOARD_ROLES:
        ampcus_org_ids_subquery = select(Organization.id).where(
            func.lower(func.replace(Organization.name, " ", "")).in_(
                ["ampcustech", "ampcustechinhouse", "ampcustechclient"]
            )
        )
        stmt = stmt.where(CandidateStart.organization_id.notin_(ampcus_org_ids_subquery))
    return stmt


@router.get("")
async def get_dashboard(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    month_start = today.replace(day=1)
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = date(today.year, quarter_month, 1)

    pending_for_role = PENDING_STATUSES
    if current_user.role.code in {"HOD", "MANAGER"}:
        pending_for_role = ("SUBMITTED", "MANAGER_REVIEW")
    elif current_user.role.code in ONBOARD_ROLES:
        pending_for_role = tuple(ONBOARD_REVIEWABLE_STATUSES)

    total_stmt = _scope_starts(
        select(
            func.count(CandidateStart.id),
            func.coalesce(
                func.sum(CandidateStart.margin).filter(
                    CandidateStart.status.in_(APPROVED_STATUSES)
                ),
                0,
            ),
            func.count(CandidateStart.id).filter(
                CandidateStart.status.in_(pending_for_role)
            ),
            func.count(CandidateStart.id).filter(
                CandidateStart.status.in_(APPROVED_STATUSES)
            ),
            func.coalesce(
                func.sum(CandidateStart.margin).filter(
                    CandidateStart.start_date >= month_start,
                    CandidateStart.status.in_(APPROVED_STATUSES),
                ),
                0,
            ),
            func.coalesce(
                func.sum(CandidateStart.margin).filter(
                    CandidateStart.start_date >= quarter_start,
                    CandidateStart.status.in_(APPROVED_STATUSES),
                ),
                0,
            ),
        ).where(CandidateStart.is_deleted.is_(False)),
        current_user,
    )
    total, total_margin, pending, approved, monthly_margin, quarterly_margin = (
        await db.execute(total_stmt)
    ).one()

    total_users = 0
    active_recruiters = 0
    if current_user.role and current_user.role.code == "MIS":
        total_users = int(
            await db.scalar(select(func.count(User.id)).where(User.deleted_at.is_(None))) or 0
        )
        active_recruiters = int(
            await db.scalar(
                select(func.count(User.id))
                .join(Role, User.role_id == Role.id)
                .where(
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    Role.code == "RECRUITER",
                )
            )
            or 0
        )

    own_starts = 0
    if is_leadership_role(current_user.role.code) or current_user.role.code in ONBOARD_ROLES:
        own_starts = int(
            await db.scalar(
                select(func.count(CandidateStart.id)).where(
                    CandidateStart.is_deleted.is_(False),
                    or_(
                        CandidateStart.recruiter_id == current_user.id,
                        func.lower(CandidateStart.user_email) == current_user.email.lower(),
                    ),
                )
            )
            or 0
        )

    return {
        "totalStarts": int(total or 0),
        "pendingStarts": int(pending or 0),
        "approvedStarts": int(approved or 0),
        "totalMargin": float(total_margin or 0),
        "monthlyMargin": float(monthly_margin or 0),
        "quarterlyMargin": float(quarterly_margin or 0),
        "totalUsers": total_users,
        "activeRecruiters": active_recruiters,
        "ownStarts": own_starts,
    }
