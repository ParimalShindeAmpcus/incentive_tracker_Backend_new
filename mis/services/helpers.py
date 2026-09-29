"""Shared helpers for API layer."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mis.core.security import ROLE_CODE_TO_UI, UI_ROLE_TO_CODE
from mis.models import (
    ImportedJobDivaRecord,
    OnboardingOrganization,
    Organization,
    RecruiterManagerMapping,
    Role,
    User,
)


def format_date(value: date | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def location_str(city: str | None, state: str | None) -> str:
    parts = [p for p in (city, state) if p]
    return ", ".join(parts)


def imported_to_start_response(record: ImportedJobDivaRecord) -> dict[str, Any]:
    return {
        "activityId": record.activity_id,
        "candidateName": record.candidate_full_name or "",
        "candidateEmail": record.candidate_email or "",
        "candidateContact": record.candidate_mobile_phone or "",
        "startDate": format_date(record.start_date),
        "endDate": format_date(record.end_date),
        "clientName": record.job_company or "",
        "endClientName": record.end_client_name or "",
        "reqId": record.jobdiva_ref_no or "",
        "jobTitle": record.job_title or "",
        "workLocation": location_str(record.work_city, record.work_state),
        "candidateLocation": location_str(record.candidate_city, record.candidate_state),
        "workAuthorization": record.work_authorization or "",
        "recruiterName": record.recruited_by or record.recruiter_email or "",
    }


async def resolve_role(db: AsyncSession, role_input: str) -> Role:
    code = UI_ROLE_TO_CODE.get(role_input.strip(), role_input.strip().upper())
    result = await db.execute(select(Role).where(Role.code == code))
    role = result.scalar_one_or_none()
    if not role:
        raise ValueError(f"Unknown role: {role_input}")
    return role


async def resolve_organization(db: AsyncSession, name_or_code: str) -> Organization:
    normalized = name_or_code.strip()
    result = await db.execute(
        select(Organization).where(
            or_(
                func.lower(Organization.name) == normalized.lower(),
                func.lower(Organization.code) == normalized.lower().replace(" ", ""),
            ),
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise ValueError(f"Organization not found: {name_or_code}")
    return org


async def get_manager_for_recruiter(db: AsyncSession, recruiter_id: int) -> User | None:
    result = await db.execute(
        select(RecruiterManagerMapping)
        .where(
            RecruiterManagerMapping.recruiter_id == recruiter_id,
            RecruiterManagerMapping.is_active.is_(True),
        )
        .limit(1)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        return None
    mgr_result = await db.execute(select(User).where(User.id == mapping.manager_id))
    return mgr_result.scalar_one_or_none()


async def find_user_by_name(
    db: AsyncSession,
    name: str,
    *,
    prefer_role_codes: frozenset[str] | set[str] | None = None,
) -> User | None:
    """Resolve a user by full name or disambiguated label.

    Supports plain names and labels like ``Full Name (email@x.com)`` when multiple
    users share the same display name. Email is the unique key — duplicate names are allowed.
    """
    raw = (name or "").strip()
    if not raw:
        return None

    # Prefer email when present in "Name (email)" / "Name <email>" / bare email
    email_match = re.search(r"[<\(]\s*([^>)\s]+@[^>)\s]+)\s*[>\)]", raw)
    email = (email_match.group(1) if email_match else raw if "@" in raw and " " not in raw else "").lower()
    if email:
        result = await db.execute(
            select(User).where(func.lower(User.email) == email, User.deleted_at.is_(None)).limit(1)
        )
        found = result.scalar_one_or_none()
        if found:
            return found

    display_name = re.sub(r"\s*[<\(][^>)]+[>\)]\s*$", "", raw).strip() or raw
    stmt = select(User).where(
        func.lower(User.full_name) == display_name.lower(),
        User.deleted_at.is_(None),
    )
    if prefer_role_codes:
        stmt = stmt.outerjoin(Role, User.role_id == Role.id).order_by(
            Role.code.in_(tuple(prefer_role_codes)).desc(),
            User.is_active.desc(),
            User.id.asc(),
        )
    else:
        stmt = stmt.order_by(User.is_active.desc(), User.id.asc())

    result = await db.execute(stmt.limit(1))
    return result.scalar_one_or_none()


async def user_to_list_item(db: AsyncSession, user: User) -> dict[str, Any]:
    manager = None
    if user.role.code == "RECRUITER":
        manager = await get_manager_for_recruiter(db, user.id)

    onboarding_org_name = ""
    if user.onboarding_organization_id:
        onboard_org = await db.get(OnboardingOrganization, user.onboarding_organization_id)
        if onboard_org and onboard_org.deleted_at is None:
            onboarding_org_name = onboard_org.name

    return {
        "id": str(user.id),
        "name": user.full_name,
        "email": user.email,
        "role": ROLE_CODE_TO_UI.get(user.role.code, user.role.name),
        "team": user.team_name or "",
        "manager": manager.full_name if manager else "",
        "organization": user.organization.name if user.organization else "",
        "onboarding_organization": onboarding_org_name,
        "status": "Active" if user.is_active else "Disabled",
    }


async def resolve_onboarding_organization(
    db: AsyncSession, name_or_code: str
) -> OnboardingOrganization:
    normalized = name_or_code.strip()
    result = await db.execute(
        select(OnboardingOrganization).where(
            or_(
                func.lower(OnboardingOrganization.name) == normalized.lower(),
                func.lower(OnboardingOrganization.code) == normalized.lower().replace(" ", ""),
            ),
            OnboardingOrganization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise ValueError(f"Onboarding organization not found: {name_or_code}")
    return org


async def get_onboarding_org_ids_for_user(db: AsyncSession, user: User) -> list[int]:
    """Regular organization IDs covered by the user's onboarding organization."""
    if not user.onboarding_organization_id:
        return []
    from mis.models import OnboardingOrganizationMapping

    result = await db.execute(
        select(OnboardingOrganizationMapping.organization_id).where(
            OnboardingOrganizationMapping.onboarding_organization_id
            == user.onboarding_organization_id
        )
    )
    return [row[0] for row in result.all()]


async def load_user_with_relations(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(User.id == user_id, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()
