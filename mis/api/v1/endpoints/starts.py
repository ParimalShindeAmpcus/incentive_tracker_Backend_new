from datetime import date
from decimal import Decimal
import re
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user
from mis.core.constants import (
    ADMIN_REVIEWABLE_STATUSES,
    HOD_APPROVER_ROLES,
    HOD_LIKE_ROLES,
    HOD_REVIEWABLE_STATUSES,
    ONBOARD_ROLES,
    ONBOARD_REVIEWABLE_STATUSES,
    calculate_margin,
    is_leadership_role,
)
from mis.db.session import get_db
from mis.models import CandidateStart, ImportedJobDivaRecord, Organization, Role, User
from mis.services.helpers import (
    find_user_by_name,
    format_date,
    get_manager_for_recruiter,
    get_onboarding_org_ids_for_user,
    imported_to_start_response,
    resolve_organization,
)
from mis.services.audit_service import start_audit_snapshot, write_audit_log
from mis.services.start_scoping import (
    build_start_visibility_conditions,
    can_user_edit_start,
    can_user_review_start,
    can_user_view_start,
)

class StartReviewBody(BaseModel):
    comments: str | None = None


CommercialValue = Annotated[
    Decimal,
    Field(ge=0, max_digits=15, decimal_places=3),
]


class StartAdminUpdateBody(BaseModel):
    candidate_name: str | None = Field(default=None, alias="candidate")
    candidate_email: str | None = Field(default=None, alias="email")
    candidate_contact_no: str | None = Field(default=None, alias="candidateContact")
    client_name: str | None = Field(default=None, alias="client")
    end_client_name: str | None = Field(default=None, alias="endClient")
    job_title: str | None = Field(default=None, alias="jobTitle")
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    req_id: str | None = Field(default=None, alias="reqId")
    contract_type: str | None = Field(default=None, alias="contractType")
    sub_contractor_company: str | None = Field(default=None, alias="subContractorCompany")
    sub_contractor_email: str | None = Field(default=None, alias="subContractorEmail")
    sub_contractor_contact: str | None = Field(default=None, alias="subContractorContact")
    job_level: str | None = Field(default=None, alias="jobLevel")
    salary: CommercialValue | None = None
    pay_rate: CommercialValue | None = Field(default=None, alias="payRate")
    taxes: CommercialValue | None = None
    benefits: CommercialValue | None = None
    referral_fee: CommercialValue | None = Field(default=None, alias="referralFee")
    gross_bill_rate: CommercialValue | None = Field(default=None, alias="grossBillRate")
    msp_fee: CommercialValue | None = Field(default=None, alias="mspFee")
    margin: CommercialValue | None = None
    remote_position: bool | None = Field(default=None, alias="remotePosition")
    work_location: str | None = Field(default=None, alias="workLocation")
    candidate_location: str | None = Field(default=None, alias="candidateLocation")
    work_authorization: str | None = Field(default=None, alias="workAuthorization")
    resume_source: str | None = Field(default=None, alias="resumeSource")
    team_lead: str | None = Field(default=None, alias="teamLead")
    crm: str | None = None
    team_manager: str | None = Field(default=None, alias="teamManager")
    head_of_department: str | None = Field(default=None, alias="headOfDepartment")
    senior_manager: str | None = Field(default=None, alias="seniorManager")
    associate_director: str | None = Field(default=None, alias="associateDirector")
    director: str | None = None
    center_head: str | None = Field(default=None, alias="centerHead")
    assistant_vice_president: str | None = Field(default=None, alias="assistantVicePresident")
    onboarding_coordinator: str | None = Field(default=None, alias="onboardingCoordinator")
    user_email: str | None = Field(default=None, alias="userEmail")
    recruiter_location: str | None = Field(default=None, alias="recruiterLocation")
    organization_name: str | None = Field(default=None, alias="organization")

HOD_REVIEWABLE_STATUSES_SET = set(HOD_REVIEWABLE_STATUSES)
ONBOARD_REVIEWABLE_STATUSES_SET = set(ONBOARD_REVIEWABLE_STATUSES)
ADMIN_REVIEWABLE_STATUSES_SET = set(ADMIN_REVIEWABLE_STATUSES)
REVIEWABLE_STATUSES = (
    HOD_REVIEWABLE_STATUSES_SET | ONBOARD_REVIEWABLE_STATUSES_SET | ADMIN_REVIEWABLE_STATUSES_SET
)
# Starts onboard may review/view: submitted by recruiters or HOD-like roles
_NOT_APPLICABLE_VALUES = {"NA", "N/A", "NOT APPLICABLE"}


async def _insert_start_notification(
    db: AsyncSession,
    *,
    user_id: int | None,
    start_id: int,
    notif_type: str,
    title: str,
    message: str,
    once: bool = False,
) -> None:
    if not user_id:
        return
    params = {
        "user_id": user_id,
        "start_id": start_id,
        "type": notif_type,
        "title": title,
        "message": message,
    }
    if once:
        existing = await db.execute(
            text(
                """
                SELECT 1 FROM notifications
                WHERE user_id = :user_id
                  AND candidate_start_id = :start_id
                  AND type = :type
                LIMIT 1
                """
            ),
            params,
        )
        if existing.first():
            return
    await db.execute(
        text(
            """
            INSERT INTO notifications (user_id, candidate_start_id, type, title, message)
            VALUES (:user_id, :start_id, :type, :title, :message)
            """
        ),
        params,
    )


def _pending_notification_copy(status: str, candidate_label: str) -> tuple[str, str] | None:
    if status in REVIEWABLE_STATUSES:
        return (
            "Start pending approval",
            f"Your start for {candidate_label} is pending approval.",
        )
    return None


def _reviewer_change_copy(actor: User, candidate_label: str) -> tuple[str, str] | None:
    role_code = actor.role.code if actor.role else ""
    if role_code in HOD_APPROVER_ROLES:
        actor_label = "HOD"
    elif role_code in ONBOARD_ROLES:
        actor_label = "onboarding"
    else:
        return None
    return (
        "Start updated — please review",
        (
            f"Something was changed in your start for {candidate_label} "
            f"by {actor.full_name} ({actor_label}). Please review it."
        ),
    )


def _is_not_applicable(value: str | None) -> bool:
    return (value or "").strip().upper() in _NOT_APPLICABLE_VALUES


def _is_ampcus_tech_name(name: str | None) -> bool:
    return (name or "").replace(" ", "").lower() in ["ampcustech", "ampcustechinhouse", "ampcustechclient"]


def _validate_mobile_phone(value: str | None, *, required: bool = False) -> None:
    phone = (value or "").strip()
    if not phone:
        if required:
            raise HTTPException(status_code=400, detail="Candidate phone number is required")
        return
    if not re.fullmatch(r"\d{1,14}", phone):
        raise HTTPException(
            status_code=400,
            detail="Candidate phone number must contain up to 14 digits",
        )


async def _get_start_or_404(db: AsyncSession, start_id: int) -> CandidateStart:
    start = await db.get(CandidateStart, start_id)
    if not start or start.is_deleted:
        raise HTTPException(status_code=404, detail="Start not found")
    return start


async def _can_view_start(db: AsyncSession, start: CandidateStart, user: User) -> bool:
    org = await db.get(Organization, start.organization_id)
    is_ampcus = _is_ampcus_tech_name(org.name if org else None)
    return can_user_view_start(start, user, is_ampcus_tech=is_ampcus)


async def _can_review_start(db: AsyncSession, start: CandidateStart, user: User) -> bool:
    org = await db.get(Organization, start.organization_id)
    is_ampcus = _is_ampcus_tech_name(org.name if org else None)
    return can_user_review_start(start, user, is_ampcus_tech=is_ampcus)


async def _can_edit_start(db: AsyncSession, start: CandidateStart, user: User) -> bool:
    org = await db.get(Organization, start.organization_id)
    is_ampcus = _is_ampcus_tech_name(org.name if org else None)
    return can_user_edit_start(start, user, is_ampcus_tech=is_ampcus)


def _approval_target_status(
    actor: User, is_ampcus_tech: bool = False, current_status: str | None = None
) -> str:
    role_code = actor.role.code if actor.role else ""
    if role_code in ONBOARD_ROLES or role_code == "MIS":
        return "APPROVED"
    if current_status in HOD_REVIEWABLE_STATUSES_SET or role_code in HOD_APPROVER_ROLES:
        if is_ampcus_tech:
            return "APPROVED"
        return "ONBOARDING_REVIEW"
    return "APPROVED"


async def _apply_start_review(
    db: AsyncSession,
    *,
    start: CandidateStart,
    actor: User,
    new_status: str,
    action: str,
    comments: str | None = None,
) -> CandidateStart:
    if start.status not in REVIEWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot review start in status {start.status}",
        )
    if not await _can_review_start(db, start, actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to review this start")
    role_code = actor.role.code if actor.role else ""
    if start.recruiter_id == actor.id and role_code in HOD_LIKE_ROLES | ONBOARD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve or reject your own submission",
        )

    org = await db.get(Organization, start.organization_id)
    is_ampcus = _is_ampcus_tech_name(org.name if org else None)

    # Enforce stage-correct approvals
    if is_ampcus and role_code in ONBOARD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Onboarding team does not review Ampcus Tech starts",
        )
    if is_ampcus and (actor.role and actor.role.code == "MIS"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin does not review or approve Ampcus Tech starts",
        )
    is_acting_as_hod = (
        role_code in HOD_APPROVER_ROLES
        or start.submission_manager_id == actor.id
        or (start.head_of_department or "").strip().lower() == actor.full_name.strip().lower()
    )
    if is_acting_as_hod and start.status not in HOD_REVIEWABLE_STATUSES_SET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This start is not pending HOD review",
        )
    if role_code in ONBOARD_ROLES and not is_acting_as_hod and start.status not in ONBOARD_REVIEWABLE_STATUSES_SET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This start is not pending onboarding review",
        )

    from_status = start.status
    before = start_audit_snapshot(start)
    start.status = new_status
    start.updated_by = actor.id

    await db.execute(
        text(
            """
            INSERT INTO approvals (candidate_start_id, action, from_status, to_status, actor_id, comments)
            VALUES (:start_id, :action, :from_status, :to_status, :actor_id, :comments)
            """
        ),
        {
            "start_id": start.id,
            "action": action,
            "from_status": from_status,
            "to_status": new_status,
            "actor_id": actor.id,
            "comments": comments,
        },
    )
    if action == "APPROVE" and is_acting_as_hod:
        if is_ampcus:
            await _insert_start_notification(
                db,
                user_id=start.recruiter_id,
                start_id=start.id,
                notif_type="START_APPROVED",
                title="Start approved",
                message=(
                    f"Your start for {start.candidate_name or start.activity_id} "
                    f"was approved by {actor.full_name} (HOD)."
                ),
            )
        else:
            await _insert_start_notification(
                db,
                user_id=start.recruiter_id,
                start_id=start.id,
                notif_type="START_APPROVED",
                title="Start approved by HOD",
                message=(
                    f"Your start for {start.candidate_name or start.activity_id} "
                    f"was approved by {actor.full_name} (HOD) and sent to onboarding for review."
                ),
            )
    elif action == "APPROVE" and role_code in ONBOARD_ROLES:
        await _insert_start_notification(
            db,
            user_id=start.recruiter_id,
            start_id=start.id,
            notif_type="START_APPROVED",
            title="Start approved by onboarding",
            message=(
                f"Your start for {start.candidate_name or start.activity_id} "
                f"was approved by {actor.full_name} (onboarding)."
            ),
        )
    elif new_status == "APPROVED":
        await _insert_start_notification(
            db,
            user_id=start.recruiter_id,
            start_id=start.id,
            notif_type="START_APPROVED",
            title="Start approved",
            message=(
                f"Your start for {start.candidate_name or start.activity_id} "
                f"was approved by {actor.full_name}."
            ),
        )


    await write_audit_log(
        db,
        actor_id=actor.id,
        organization_id=start.organization_id,
        entity_type="CANDIDATE_START",
        entity_id=start.id,
        action="STATUS_CHANGE",
        before_json=before,
        after_json=start_audit_snapshot(start),
    )
    await db.commit()
    await db.refresh(start)
    return start


router = APIRouter()


class StartCreateBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    activity_id: str = Field(alias="activityId")
    organization_name: str | None = Field(default=None, alias="organizationName")
    user_email: str | None = Field(default=None, alias="userEmail")
    team_manager: str | None = Field(default=None, alias="teamManager")
    head_of_department: str | None = Field(default=None, alias="headOfDepartment")
    status: str = "DRAFT"

    candidate_name: str | None = Field(default=None, alias="candidateName")
    candidate_email: str | None = Field(default=None, alias="candidateEmail")
    candidate_contact_no: str | None = Field(default=None, alias="candidateContactNo")
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    client_name: str | None = Field(default=None, alias="clientName")
    end_client_name: str | None = Field(default=None, alias="endClientName")
    contract_type: str | None = Field(default=None, alias="contractType")
    sub_contractor_company: str | None = Field(default=None, alias="subContractorCompany")
    sub_contractor_email: str | None = Field(default=None, alias="subContractorEmail")
    sub_contractor_contact: str | None = Field(default=None, alias="subContractorContact")
    req_id: str | None = Field(default=None, alias="reqId")
    job_title: str | None = Field(default=None, alias="jobTitle")
    job_level: str | None = Field(default=None, alias="jobLevel")
    salary: CommercialValue | None = None
    pay_rate: CommercialValue | None = Field(default=None, alias="payRate")
    taxes: CommercialValue | None = None
    benefits: CommercialValue | None = None
    referral_fee: CommercialValue | None = Field(default=None, alias="referralFee")
    gross_bill_rate: CommercialValue | None = Field(default=None, alias="grossBillRate")
    msp_fee: CommercialValue | None = Field(default=None, alias="mspFee")
    margin: CommercialValue | None = None
    margin_is_overridden: bool = Field(default=False, alias="marginIsOverridden")
    remote_position: bool | None = Field(default=None, alias="remotePosition")
    work_location: str | None = Field(default=None, alias="workLocation")
    candidate_location: str | None = Field(default=None, alias="candidateLocation")
    work_authorization: str | None = Field(default=None, alias="workAuthorization")
    resume_source: str | None = Field(default=None, alias="resumeSource")
    team_lead: str | None = Field(default=None, alias="teamLead")
    crm: str | None = None
    senior_manager: str | None = Field(default=None, alias="seniorManager")
    associate_director: str | None = Field(default=None, alias="associateDirector")
    director: str | None = None
    center_head: str | None = Field(default=None, alias="centerHead")
    assistant_vice_president: str | None = Field(default=None, alias="assistantVicePresident")
    onboarding_coordinator: str | None = Field(default=None, alias="onboardingCoordinator")
    recruiter_location: str | None = Field(default=None, alias="recruiterLocation")
    recruiter_name: str | None = Field(default=None, alias="recruiterName")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


async def _find_imported(
    db: AsyncSession,
    activity_id: str,
    *,
    for_update: bool = False,
) -> ImportedJobDivaRecord:
    normalized = activity_id.strip().lstrip("#")
    numeric = normalized.upper().replace("JD-", "").replace("JD", "")
    stmt = select(ImportedJobDivaRecord).where(
        or_(
            func.lower(ImportedJobDivaRecord.activity_id) == normalized.lower(),
            ImportedJobDivaRecord.activity_id == numeric,
            ImportedJobDivaRecord.activity_id == f"JD-{numeric}",
        )
    )
    if for_update:
        stmt = stmt.with_for_update()
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Imported JobDiva record not found")
    if record.is_consumed:
        raise HTTPException(
            status_code=409,
            detail="A start has already been submitted for this Activity ID",
        )
    return record

async def _resolve_recruiter(
    db: AsyncSession, body: StartCreateBody, current_user: User
) -> User:
    return current_user


def _start_to_record(start: CandidateStart, recruiter_name: str = "", org_name: str = "") -> dict[str, Any]:
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


@router.get("/jobdiva/{activity_id}")
async def get_start_jobdiva_lookup(
    activity_id: str,
    _current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    record = await _find_imported(db, activity_id)
    return imported_to_start_response(record)


@router.get("")
async def get_starts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500, alias="pageSize"),
    status: str | None = None,
    search: str | None = None,
):
    stmt = select(CandidateStart).where(CandidateStart.is_deleted.is_(False)).order_by(
        CandidateStart.created_at.desc()
    )

    for cond in build_start_visibility_conditions(current_user):
        stmt = stmt.where(cond)

    if current_user.role and current_user.role.code in ONBOARD_ROLES:
        ampcus_org_ids_subquery = select(Organization.id).where(
            func.lower(func.replace(Organization.name, " ", "")).in_(
                ["ampcustech", "ampcustechinhouse", "ampcustechclient"]
            )
        )
        stmt = stmt.where(CandidateStart.organization_id.notin_(ampcus_org_ids_subquery))

    if status:
        stmt = stmt.where(CandidateStart.status == status.upper())
    if search:
        q = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(CandidateStart.candidate_name).like(q),
                func.lower(CandidateStart.activity_id).like(q),
                func.lower(CandidateStart.client_name).like(q),
            )
        )

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    offset = (page - 1) * page_size
    result = await db.execute(stmt.offset(offset).limit(page_size))
    starts = result.scalars().all()

    items = []
    for s in starts:
        recruiter = await db.get(User, s.recruiter_id)
        org = await db.get(Organization, s.organization_id)
        items.append(_start_to_record(s, recruiter.full_name if recruiter else "", org.name if org else ""))

    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/{start_id}")
async def get_start(
    start_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    start = await _get_start_or_404(db, start_id)
    if not await _can_view_start(db, start, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to view this start")
    recruiter = await db.get(User, start.recruiter_id)
    return _start_to_record(start, recruiter.full_name if recruiter else "")


@router.post("")
async def create_start(
    body: StartCreateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_name = body.organization_name or "Ampcus Tech"
    is_ampcus_tech = _is_ampcus_tech_name(org_name)

    if is_ampcus_tech:
        _validate_mobile_phone(body.candidate_contact_no, required=True)
    if body.sub_contractor_contact is not None:
        _validate_mobile_phone(body.sub_contractor_contact)

    if is_ampcus_tech and not body.activity_id.strip():
        org_normalized = (org_name or "").replace(" ", "").lower()
        if org_normalized in ["ampcustechinhouse", "ampcustechclient"]:
            while True:
                new_id = f"AMPTECH-{uuid4().hex[:5].upper()}"
                exists = await db.scalar(
                    select(ImportedJobDivaRecord.activity_id)
                    .where(ImportedJobDivaRecord.activity_id == new_id)
                    .limit(1)
                )
                if not exists:
                    break
        else:
            new_id = f"AMPTECH-{uuid4().hex[:24].upper()}"

        imported = ImportedJobDivaRecord(
            activity_id=new_id,
            candidate_full_name=body.candidate_name,
            candidate_email=body.candidate_email,
            candidate_mobile_phone=body.candidate_contact_no,
            job_company=body.client_name,
            jobdiva_ref_no=body.req_id,
            recruited_by=body.recruiter_name,
            job_title=body.job_title,
            start_date=_parse_date(body.start_date),
            end_date=_parse_date(body.end_date),
            is_consumed=False,
        )
        db.add(imported)
        await db.flush()
    else:
        imported = await _find_imported(db, body.activity_id, for_update=True)

    existing_start_id = await db.scalar(
        select(CandidateStart.id)
        .where(
            func.lower(CandidateStart.activity_id) == imported.activity_id.lower(),
            CandidateStart.is_deleted.is_(False),
        )
        .limit(1)
    )
    if existing_start_id is not None:
        raise HTTPException(
            status_code=409,
            detail="A start has already been submitted for this Activity ID",
        )
    recruiter = await _resolve_recruiter(db, body, current_user)

    try:
        org = await resolve_organization(db, org_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mapped_manager = await get_manager_for_recruiter(db, recruiter.id)
    submission_manager = None

    # Enforce mandatory Head of Department for most roles (optional for Onboard Team)
    hod_name = (body.head_of_department or "").strip()
    is_onboarding_actor = current_user.role and current_user.role.code in ONBOARD_ROLES

    if not is_onboarding_actor and (not hod_name or _is_not_applicable(hod_name)):
        raise HTTPException(
            status_code=400,
            detail="Valid Head of Department is required.",
        )

    if hod_name and not _is_not_applicable(hod_name):
        named_hod = await find_user_by_name(
            db, hod_name, prefer_role_codes=HOD_LIKE_ROLES | {"MIS"}
        )
        if not named_hod:
            raise HTTPException(status_code=400, detail=f"Head of Department not found: {hod_name}")
        submission_manager = named_hod

    submit_status = body.status.upper()
    auto_comment = None
    recruiter_role = await db.get(Role, recruiter.role_id)
    if recruiter_role and submit_status == "SUBMITTED":
        if recruiter_role.code in ONBOARD_ROLES:
            submit_status = "APPROVED"
            auto_comment = "Auto-approved onboard team submission"
        elif recruiter_role.code == "HOD" or (submission_manager and submission_manager.id == recruiter.id):
            # HOD own starts skip HOD review
            if is_ampcus_tech:
                submit_status = "APPROVED"
                auto_comment = "Auto-approved HOD submission"
            else:
                submit_status = "ONBOARDING_REVIEW"
                auto_comment = "Auto-approved HOD submission — pending onboarding review"

    # Ampcus Tech: manual margin only (no server-side auto-calc)
    use_manual_margin = is_ampcus_tech or body.margin_is_overridden or body.margin is not None
    resolved_margin = (
        body.margin
        if use_manual_margin
        else calculate_margin(
            contract_type=body.contract_type,
            gross_bill_rate=body.gross_bill_rate,
            msp_fee_pct=body.msp_fee,
            pay_rate=body.pay_rate,
            tax_pct=body.taxes,
            benefits=body.benefits,
            referral_fee=body.referral_fee,
        )
    )

    start = CandidateStart(
        imported_record_id=imported.id,
        activity_id=imported.activity_id,
        organization_id=org.id,
        recruiter_id=recruiter.id,
        mapped_manager_id=mapped_manager.id if mapped_manager else None,
        submission_manager_id=submission_manager.id if submission_manager else None,
        candidate_name=body.candidate_name or imported.candidate_full_name,
        candidate_email=body.candidate_email or imported.candidate_email,
        candidate_contact_no=body.candidate_contact_no or imported.candidate_mobile_phone,
        start_date=_parse_date(body.start_date) or imported.start_date,
        end_date=_parse_date(body.end_date) or imported.end_date,
        client_name=body.client_name or imported.job_company,
        end_client_name=body.end_client_name or imported.end_client_name,
        contract_type=body.contract_type,
        sub_contractor_company=body.sub_contractor_company,
        sub_contractor_email=body.sub_contractor_email,
        sub_contractor_contact=body.sub_contractor_contact,
        req_id=body.req_id or imported.jobdiva_ref_no,
        job_title=body.job_title or imported.job_title,
        job_level=body.job_level,
        salary=body.salary,
        pay_rate=body.pay_rate,
        taxes=body.taxes,
        benefits=body.benefits,
        referral_fee=body.referral_fee,
        gross_bill_rate=body.gross_bill_rate,
        msp_fee=body.msp_fee,
        margin=resolved_margin if resolved_margin is not None else 0,
        margin_is_overridden=bool(is_ampcus_tech or body.margin_is_overridden),
        remote_position=body.remote_position,
        work_location=body.work_location,
        candidate_location=body.candidate_location,
        work_authorization=body.work_authorization or imported.work_authorization,
        resume_source=body.resume_source,
        team_lead=body.team_lead,
        crm=body.crm,
        team_manager=body.team_manager,
        head_of_department=body.head_of_department or (
            submission_manager.full_name if submission_manager else None
        ),
        senior_manager=body.senior_manager,
        associate_director=body.associate_director,
        director=body.director,
        center_head=body.center_head,
        assistant_vice_president=body.assistant_vice_president,
        onboarding_coordinator=body.onboarding_coordinator,
        user_email=body.user_email or recruiter.email,
        recruiter_location=body.recruiter_location,
        status=submit_status,
        created_by=recruiter.id,
    )
    db.add(start)
    imported.is_consumed = True
    await db.flush()

    if auto_comment and submit_status in {"APPROVED", "ONBOARDING_REVIEW", "MIS_REVIEW"}:
        await db.execute(
            text(
                """
                INSERT INTO approvals (candidate_start_id, action, from_status, to_status, actor_id, comments)
                VALUES (:start_id, 'APPROVE', 'SUBMITTED', :to_status, :actor_id, :comments)
                """
            ),
            {
                "start_id": start.id,
                "to_status": submit_status,
                "actor_id": recruiter.id,
                "comments": auto_comment,
            },
        )

    pending_copy = _pending_notification_copy(
        submit_status, start.candidate_name or start.activity_id
    )
    if pending_copy:
        title, message = pending_copy
        await _insert_start_notification(
            db,
            user_id=start.recruiter_id,
            start_id=start.id,
            notif_type="START_PENDING",
            title=title,
            message=message,
            once=True,
        )

    await db.commit()
    await db.refresh(start)
    return _start_to_record(start, recruiter.full_name, org.name)


@router.post("/{start_id}/approve")
async def approve_start(
    start_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    body: StartReviewBody = StartReviewBody(),
):
    start = await _get_start_or_404(db, start_id)
    org = await db.get(Organization, start.organization_id)
    is_ampcus_tech = _is_ampcus_tech_name(org.name if org else None)
    start = await _apply_start_review(
        db,
        start=start,
        actor=current_user,
        new_status=_approval_target_status(
            current_user, is_ampcus_tech=is_ampcus_tech, current_status=start.status
        ),
        action="APPROVE",
        comments=body.comments,
    )
    recruiter = await db.get(User, start.recruiter_id)
    return _start_to_record(start, recruiter.full_name if recruiter else "", org.name if org else "")


@router.post("/{start_id}/reject")
async def reject_start(
    start_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    body: StartReviewBody = StartReviewBody(),
):
    start = await _get_start_or_404(db, start_id)
    start = await _apply_start_review(
        db,
        start=start,
        actor=current_user,
        new_status="REJECTED",
        action="REJECT",
        comments=body.comments,
    )
    recruiter = await db.get(User, start.recruiter_id)
    org = await db.get(Organization, start.organization_id)
    return _start_to_record(start, recruiter.full_name if recruiter else "", org.name if org else "")


@router.put("/{start_id}")
async def update_start(
    start_id: int,
    body: StartAdminUpdateBody,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    start = await _get_start_or_404(db, start_id)
    if not await _can_edit_start(db, start, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this start")

    before = start_audit_snapshot(start)
    org = await db.get(Organization, start.organization_id)
    is_ampcus_tech = _is_ampcus_tech_name(org.name if org else None)
    role_code = (current_user.role.code if current_user.role else "").upper()
    is_jobdiva_readonly = (
        role_code != "MIS"
        and role_code in HOD_LIKE_ROLES | ONBOARD_ROLES
        and not is_ampcus_tech
    )

    if is_ampcus_tech and body.candidate_contact_no is not None:
        _validate_mobile_phone(body.candidate_contact_no, required=True)
    if body.sub_contractor_contact is not None:
        _validate_mobile_phone(body.sub_contractor_contact)

    if not is_jobdiva_readonly:
        start.candidate_name = body.candidate_name
        start.candidate_email = body.candidate_email
        start.candidate_contact_no = body.candidate_contact_no
        start.client_name = body.client_name
        start.end_client_name = body.end_client_name
        start.job_title = body.job_title
        start.start_date = _parse_date(body.start_date)
        start.end_date = _parse_date(body.end_date)
        start.req_id = body.req_id
        start.work_location = body.work_location
        start.candidate_location = body.candidate_location
        start.work_authorization = body.work_authorization
        start.user_email = body.user_email
        if body.organization_name:
            try:
                organization = await resolve_organization(db, body.organization_name)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            start.organization_id = organization.id

    start.contract_type = body.contract_type
    start.sub_contractor_company = body.sub_contractor_company
    start.sub_contractor_email = body.sub_contractor_email
    start.sub_contractor_contact = body.sub_contractor_contact
    start.job_level = body.job_level
    start.salary = body.salary
    start.pay_rate = body.pay_rate
    start.taxes = body.taxes
    start.benefits = body.benefits
    start.referral_fee = body.referral_fee
    start.gross_bill_rate = body.gross_bill_rate
    start.msp_fee = body.msp_fee
    start.margin = body.margin
    if is_ampcus_tech:
        start.margin_is_overridden = True
    start.remote_position = body.remote_position
    start.resume_source = body.resume_source
    start.team_lead = body.team_lead
    start.crm = body.crm
    start.team_manager = body.team_manager
    if body.head_of_department is not None:
        hod_name = body.head_of_department.strip()
        start.head_of_department = hod_name or None
        if hod_name and not _is_not_applicable(hod_name):
            named_hod = await find_user_by_name(
                db, hod_name, prefer_role_codes=HOD_LIKE_ROLES | {"MIS"}
            )
            if not named_hod:
                raise HTTPException(
                    status_code=400, detail=f"Head of Department not found: {hod_name}"
                )
            start.submission_manager_id = named_hod.id
    start.senior_manager = body.senior_manager
    start.associate_director = body.associate_director
    start.director = body.director
    start.center_head = body.center_head
    start.assistant_vice_president = body.assistant_vice_president
    start.onboarding_coordinator = body.onboarding_coordinator
    start.user_email = body.user_email
    start.recruiter_location = body.recruiter_location
    start.updated_by = current_user.id
    after = start_audit_snapshot(start)
    await write_audit_log(
        db,
        actor_id=current_user.id,
        organization_id=start.organization_id,
        entity_type="CANDIDATE_START",
        entity_id=start.id,
        action="UPDATE",
        before_json=before,
        after_json=after,
    )
    if before != after and start.recruiter_id != current_user.id:
        change_copy = _reviewer_change_copy(
            current_user, start.candidate_name or start.activity_id
        )
        if change_copy:
            title, message = change_copy
            await _insert_start_notification(
                db,
                user_id=start.recruiter_id,
                start_id=start.id,
                notif_type="START_UPDATED",
                title=title,
                message=message,
            )
    await db.commit()
    await db.refresh(start)

    recruiter = await db.get(User, start.recruiter_id)
    org = await db.get(Organization, start.organization_id)
    return _start_to_record(start, recruiter.full_name if recruiter else "", org.name if org else "")


