"""Shared analytics queries for dashboard, performance, incentives, and reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mis.models import CandidateStart, Organization, Role, User
from mis.core.constants import is_leadership_role

APPROVED_STATUSES = ("APPROVED", "COMPLETED")
INCENTIVE_RATE = 0.06
MARGIN_TARGET_PER_RECRUITER = 75_000


from mis.services.start_scoping import build_start_visibility_conditions


def scope_starts_for_user(stmt, current_user: User):
    for cond in build_start_visibility_conditions(current_user):
        stmt = stmt.where(cond)
    return stmt


async def recruiter_leaderboard(
    db: AsyncSession,
    current_user: User,
    *,
    year: int | None = None,
    month: int | None = None,
) -> list[dict[str, Any]]:
    today = date.today()
    year = year or today.year
    month = month or today.month

    stmt = (
        select(
            User.full_name,
            func.count(CandidateStart.id).label("starts"),
            func.coalesce(func.sum(CandidateStart.margin), 0).label("margin"),
        )
        .join(User, User.id == CandidateStart.recruiter_id)
        .join(Role, Role.id == User.role_id)
        .where(
            CandidateStart.is_deleted.is_(False),
            CandidateStart.status.in_(APPROVED_STATUSES),
            func.extract("year", CandidateStart.start_date) == year,
            func.extract("month", CandidateStart.start_date) == month,
            Role.code == "RECRUITER",
            User.deleted_at.is_(None),
        )
        .group_by(User.id, User.full_name)
        .order_by(func.coalesce(func.sum(CandidateStart.margin), 0).desc())
    )
    stmt = scope_starts_for_user(stmt, current_user)
    rows = (await db.execute(stmt)).all()

    leaderboard: list[dict[str, Any]] = []
    for row in rows:
        margin = float(row.margin or 0)
        incentive = round(margin * INCENTIVE_RATE, 2)
        attainment = min(200, round((margin / MARGIN_TARGET_PER_RECRUITER) * 100)) if margin else 0
        leaderboard.append(
            {
                "name": row.full_name,
                "starts": int(row.starts or 0),
                "margin": margin,
                "incentive": incentive,
                "attainment": attainment,
            }
        )
    return leaderboard


async def monthly_margin_trend(
    db: AsyncSession,
    current_user: User,
    months: int = 8,
) -> list[dict[str, Any]]:
    today = date.today()
    results: list[dict[str, Any]] = []
    for offset in range(months - 1, -1, -1):
        m = today.month - offset
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        stmt = select(
            func.count(CandidateStart.id),
            func.coalesce(func.sum(CandidateStart.margin), 0),
        ).where(
            CandidateStart.is_deleted.is_(False),
            CandidateStart.status.in_(APPROVED_STATUSES),
            func.extract("year", CandidateStart.start_date) == y,
            func.extract("month", CandidateStart.start_date) == m,
        )
        stmt = scope_starts_for_user(stmt, current_user)
        count, margin = (await db.execute(stmt)).one()
        month_label = date(y, m, 1).strftime("%b")
        results.append(
            {
                "month": month_label,
                "starts": int(count or 0),
                "margin": float(margin or 0),
            }
        )
    return results


async def incentive_summary(db: AsyncSession, current_user: User) -> dict[str, Any]:
    today = date.today()
    leaderboard = await recruiter_leaderboard(db, current_user, year=today.year, month=today.month)
    monthly_trend = await monthly_margin_trend(db, current_user)

    month_payout = sum(r["incentive"] for r in leaderboard)
    ytd_payout = sum(round(m["margin"] * INCENTIVE_RATE, 2) for m in monthly_trend)
    avg_per = round(month_payout / len(leaderboard), 2) if leaderboard else 0.0

    return {
        "monthlyPayout": month_payout,
        "ytdPayout": ytd_payout,
        "avgPerRecruiter": avg_per,
        "monthlyTrend": [
            {**m, "incentive": round(m["margin"] * INCENTIVE_RATE, 2)} for m in monthly_trend
        ],
        "leaderboard": leaderboard,
    }
