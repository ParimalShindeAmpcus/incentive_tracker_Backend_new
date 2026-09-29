from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from mis.api.v1.dependencies.auth import require_roles
from mis.core import rbac
from mis.db.session import get_db
from mis.models import CandidateStart, Organization, User
from mis.services.analytics_service import scope_starts_for_user
from mis.services.helpers import format_date

router = APIRouter()


def _parse_query_date(value: str) -> date:
    return date.fromisoformat(value)


def _start_to_report_row(start: CandidateStart, recruiter_name: str, org_name: str) -> dict:
    """Full start payload — same fields as Starts list/export."""
    return {
        "id": str(start.id),
        "activityId": start.activity_id,
        "candidate": start.candidate_name or "",
        "email": start.candidate_email or "",
        "client": start.client_name or "",
        "endClient": start.end_client_name or "",
        "jobTitle": start.job_title or "",
        "startDate": format_date(start.start_date),
        "margin": float(start.margin or 0),
        "status": str(start.status),
        "recruiter": recruiter_name,
        "organization": org_name,
        "workLocation": start.work_location or "",
        "candidateContact": start.candidate_contact_no or "",
        "endDate": format_date(start.end_date),
        "reqId": start.req_id or "",
        "contractType": start.contract_type or "",
        "subContractorCompany": start.sub_contractor_company or "",
        "subContractorEmail": start.sub_contractor_email or "",
        "subContractorContact": start.sub_contractor_contact or "",
        "jobLevel": start.job_level or "",
        "salary": float(start.salary) if start.salary is not None else None,
        "payRate": float(start.pay_rate) if start.pay_rate is not None else None,
        "taxes": float(start.taxes) if start.taxes is not None else None,
        "benefits": float(start.benefits) if start.benefits is not None else None,
        "referralFee": float(start.referral_fee) if start.referral_fee is not None else None,
        "grossBillRate": float(start.gross_bill_rate) if start.gross_bill_rate is not None else None,
        "mspFee": float(start.msp_fee) if start.msp_fee is not None else None,
        "remotePosition": start.remote_position,
        "candidateLocation": start.candidate_location or "",
        "workAuthorization": start.work_authorization or "",
        "resumeSource": start.resume_source or "",
        "teamLead": start.team_lead or "",
        "crm": start.crm or "",
        "teamManager": start.team_manager or "",
        "headOfDepartment": start.head_of_department or "",
        "seniorManager": start.senior_manager or "",
        "associateDirector": start.associate_director or "",
        "director": start.director or "",
        "centerHead": start.center_head or "",
        "assistantVicePresident": start.assistant_vice_president or "",
        "onboardingCoordinator": start.onboarding_coordinator or "",
        "userEmail": start.user_email or "",
        "recruiterLocation": start.recruiter_location or "",
    }


@router.get("/filter-options")
async def get_report_filter_options(
    current_user: Annotated[User, Depends(require_roles(*rbac.ADMIN_ONLY))],
    db: AsyncSession = Depends(get_db),
):
    """Distinct clients / organizations from starts for report filter dropdowns."""
    client_stmt = (
        select(CandidateStart.client_name)
        .where(
            CandidateStart.is_deleted.is_(False),
            CandidateStart.client_name.is_not(None),
            CandidateStart.client_name != "",
        )
        .distinct()
        .order_by(CandidateStart.client_name)
    )
    client_stmt = scope_starts_for_user(client_stmt, current_user)
    clients = [row[0] for row in (await db.execute(client_stmt)).all() if row[0]]

    org_stmt = (
        select(Organization.name)
        .join(CandidateStart, CandidateStart.organization_id == Organization.id)
        .where(
            CandidateStart.is_deleted.is_(False),
            Organization.deleted_at.is_(None),
        )
        .distinct()
        .order_by(Organization.name)
    )
    org_stmt = scope_starts_for_user(org_stmt, current_user)
    organizations = [row[0] for row in (await db.execute(org_stmt)).all() if row[0]]

    return {"clients": clients, "organizations": organizations}


@router.get("")
async def get_reports(
    current_user: Annotated[User, Depends(require_roles(*rbac.ADMIN_ONLY))],
    db: AsyncSession = Depends(get_db),
    from_date: str | None = Query(None, alias="fromDate"),
    to_date: str | None = Query(None, alias="toDate"),
    organization: str | None = None,
    client: str | None = None,
    recruiter: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    RecruiterUser = aliased(User)

    stmt = (
        select(CandidateStart)
        .outerjoin(RecruiterUser, RecruiterUser.id == CandidateStart.recruiter_id)
        .outerjoin(Organization, Organization.id == CandidateStart.organization_id)
        .where(CandidateStart.is_deleted.is_(False))
        .order_by(CandidateStart.start_date.desc().nullslast(), CandidateStart.id.desc())
    )
    stmt = scope_starts_for_user(stmt, current_user)

    if from_date:
        stmt = stmt.where(CandidateStart.start_date >= _parse_query_date(from_date))
    if to_date:
        stmt = stmt.where(CandidateStart.start_date <= _parse_query_date(to_date))
    if organization and organization != "all":
        stmt = stmt.where(func.lower(Organization.name) == organization.lower())
    if client and client != "all":
        stmt = stmt.where(func.lower(CandidateStart.client_name) == client.lower())
    if recruiter and recruiter != "all":
        stmt = stmt.where(func.lower(RecruiterUser.full_name) == recruiter.lower())
    if status and status != "all":
        status_upper = status.upper()
        if status_upper == "SUBMITTED":
            stmt = stmt.where(
                CandidateStart.status.in_(("SUBMITTED", "MANAGER_REVIEW"))
            )
        elif status_upper == "ONBOARDING_REVIEW":
            stmt = stmt.where(CandidateStart.status == "ONBOARDING_REVIEW")
        elif status_upper == "MIS_REVIEW":
            stmt = stmt.where(CandidateStart.status == "MIS_REVIEW")
        elif status_upper == "APPROVED":
            stmt = stmt.where(CandidateStart.status.in_(("APPROVED", "COMPLETED")))
        else:
            stmt = stmt.where(CandidateStart.status == status_upper)
    if search:
        q = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(CandidateStart.candidate_name, "")).like(q),
                func.lower(func.coalesce(CandidateStart.job_title, "")).like(q),
                func.lower(func.coalesce(CandidateStart.client_name, "")).like(q),
                func.lower(func.coalesce(CandidateStart.end_client_name, "")).like(q),
                func.lower(func.coalesce(CandidateStart.activity_id, "")).like(q),
                func.lower(func.coalesce(RecruiterUser.full_name, "")).like(q),
                func.lower(func.coalesce(Organization.name, "")).like(q),
            )
        )

    starts = (await db.execute(stmt)).scalars().unique().all()
    items = []
    total_margin = 0.0
    for start in starts:
        recruiter_user = await db.get(User, start.recruiter_id)
        org = await db.get(Organization, start.organization_id)
        margin = float(start.margin or 0)
        if start.status in ("APPROVED", "COMPLETED"):
            total_margin += margin
        items.append(
            _start_to_report_row(
                start,
                recruiter_user.full_name if recruiter_user else "",
                org.name if org else "",
            )
        )

    return {
        "items": items,
        "total": len(items),
        "totalMargin": total_margin,
        "totalStarts": len(items),
    }
