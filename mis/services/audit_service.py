"""Write and query audit_logs."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mis.models import User

START_FIELD_LABELS: dict[str, str] = {
    "activityId": "Activity ID",
    "candidateName": "Candidate Name",
    "candidateEmail": "Candidate Email ID",
    "candidateContactNo": "Candidate Contact No",
    "clientName": "Client Name",
    "endClientName": "End Client Name",
    "jobTitle": "Job Title",
    "startDate": "Start Date",
    "endDate": "End Date",
    "reqId": "Req ID",
    "contractType": "Contract Type",
    "subContractorCompany": "Sub-Contractor Company",
    "subContractorEmail": "Sub-Contractor Email",
    "subContractorContact": "Sub-Contractor Contact",
    "jobLevel": "Job Level",
    "salary": "Salary",
    "payRate": "Pay Rate / Hr",
    "taxes": "Taxes / Admin / Payroll Charges",
    "benefits": "Health Benefit",
    "referralFee": "Referral Fee",
    "grossBillRate": "Gross Bill Rate (before MSP)",
    "mspFee": "MSP / VMS Fees",
    "margin": "Margin / Hr",
    "remotePosition": "Remote Position",
    "workLocation": "Work Location",
    "candidateLocation": "Candidate Location",
    "workAuthorization": "Candidate Work Authorization",
    "resumeSource": "Resume Source",
    "teamLead": "Team Lead",
    "crm": "CRM",
    "teamManager": "Team Manager",
    "seniorManager": "Senior Manager",
    "associateDirector": "Associate Director",
    "director": "Director",
    "centerHead": "Center Head",
    "assistantVicePresident": "Assistant Vice President",
    "onboardingCoordinator": "Onboarding Coordinator",
    "userEmail": "User Email",
    "recruiterLocation": "Recruiter Location",
    "status": "Status",
}

USER_FIELD_LABELS: dict[str, str] = {
    "fullName": "Full Name",
    "email": "Email",
    "team": "Team",
    "isActive": "Active",
    "organizationId": "Organization ID",
    "roleId": "Role ID",
}


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _format_audit_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _field_label(entity_type: str, key: str) -> str:
    if entity_type == "CANDIDATE_START":
        return START_FIELD_LABELS.get(key, key)
    if entity_type == "USER":
        return USER_FIELD_LABELS.get(key, key)
    return key


def _expand_field_changes(
    *,
    log_id: int,
    entity_type: str,
    activity_id: str,
    actor_name: str,
    created_at: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    keys = sorted(set(before.keys()) | set(after.keys()))
    rows: list[dict[str, Any]] = []
    for key in keys:
        old_value = before.get(key)
        new_value = after.get(key)
        if json.dumps(old_value, sort_keys=True, default=str) == json.dumps(
            new_value, sort_keys=True, default=str
        ):
            continue
        rows.append(
            {
                "id": f"{log_id}:{key}",
                "activityId": activity_id,
                "field": _field_label(entity_type, key),
                "changedBy": actor_name,
                "changedAt": created_at,
                "oldValue": _format_audit_value(old_value),
                "newValue": _format_audit_value(new_value),
            }
        )
    return rows


async def write_audit_log(
    db: AsyncSession,
    *,
    actor_id: int | None,
    entity_type: str,
    entity_id: int | None,
    action: str,
    before_json: dict[str, Any] | None = None,
    after_json: dict[str, Any] | None = None,
    organization_id: int | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO audit_logs
                (organization_id, actor_id, entity_type, entity_id, action, before_json, after_json)
            VALUES
                (:organization_id, :actor_id, :entity_type, :entity_id, :action, :before_json, :after_json)
            """
        ),
        {
            "organization_id": organization_id,
            "actor_id": actor_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "before_json": json.dumps(before_json) if before_json is not None else None,
            "after_json": json.dumps(after_json) if after_json is not None else None,
        },
    )


async def list_audit_logs(
    db: AsyncSession,
    *,
    limit: int = 200,
    organization_id: int | None = None,
    entity_type: str | None = None,
    activity_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    from datetime import date as date_cls, datetime, time, timezone

    stmt = """
        SELECT
            al.id,
            al.entity_type,
            al.entity_id,
            al.action,
            al.before_json,
            al.after_json,
            al.created_at,
            u.full_name AS actor_name,
            cs.activity_id AS start_activity_id
        FROM audit_logs al
        LEFT JOIN users u ON u.id = al.actor_id
        LEFT JOIN candidate_start cs
            ON cs.id = al.entity_id AND al.entity_type = 'CANDIDATE_START'
    """
    params: dict[str, Any] = {"limit": limit}
    clauses: list[str] = []
    # Tenant isolation: restrict non-super-admin users to their own organization's logs.
    if organization_id is not None:
        clauses.append("al.organization_id = :organization_id")
        params["organization_id"] = organization_id
    if entity_type:
        clauses.append("al.entity_type = :entity_type")
        params["entity_type"] = entity_type
    if from_date:
        start_day = date_cls.fromisoformat(from_date.strip())
        clauses.append("al.created_at >= :from_date")
        params["from_date"] = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
    if to_date:
        end_day = date_cls.fromisoformat(to_date.strip())
        clauses.append("al.created_at <= :to_date")
        params["to_date"] = datetime.combine(end_day, time.max, tzinfo=timezone.utc)
    if activity_id and activity_id.strip():
        clauses.append(
            """(
                LOWER(COALESCE(cs.activity_id, '')) LIKE :activity_id
                OR LOWER(COALESCE(al.before_json::text, '')) LIKE :activity_id
                OR LOWER(COALESCE(al.after_json::text, '')) LIKE :activity_id
                OR CAST(al.entity_id AS text) LIKE :activity_id
            )"""
        )
        params["activity_id"] = f"%{activity_id.strip().lower()}%"
    if clauses:
        stmt += " WHERE " + " AND ".join(clauses)
    stmt += " ORDER BY al.created_at DESC LIMIT :limit"

    rows = (await db.execute(text(stmt), params)).mappings().all()
    field_rows: list[dict[str, Any]] = []
    for row in rows:
        before = _as_dict(row["before_json"])
        after = _as_dict(row["after_json"])
        created_at = row["created_at"].isoformat() if row["created_at"] else ""
        actor_name = row["actor_name"] or "System"
        activity = (
            after.get("activityId")
            or before.get("activityId")
            or row["start_activity_id"]
            or (str(row["entity_id"]) if row["entity_type"] == "USER" and row["entity_id"] else "")
            or "-"
        )
        if activity_id and activity_id.strip():
            needle = activity_id.strip().lower()
            if needle not in str(activity).lower():
                continue
        field_rows.extend(
            _expand_field_changes(
                log_id=row["id"],
                entity_type=row["entity_type"],
                activity_id=str(activity),
                actor_name=actor_name,
                created_at=created_at,
                before=before,
                after=after,
            )
        )
    return field_rows[:limit]


def start_audit_snapshot(start) -> dict[str, Any]:
    return {
        "activityId": start.activity_id,
        "candidateName": start.candidate_name,
        "candidateEmail": start.candidate_email,
        "candidateContactNo": start.candidate_contact_no,
        "clientName": start.client_name,
        "endClientName": start.end_client_name,
        "jobTitle": start.job_title,
        "startDate": start.start_date.isoformat() if start.start_date else None,
        "endDate": start.end_date.isoformat() if start.end_date else None,
        "reqId": start.req_id,
        "contractType": start.contract_type,
        "jobLevel": start.job_level,
        "salary": float(start.salary) if start.salary is not None else None,
        "payRate": float(start.pay_rate) if start.pay_rate is not None else None,
        "taxes": float(start.taxes) if start.taxes is not None else None,
        "benefits": float(start.benefits) if start.benefits is not None else None,
        "referralFee": float(start.referral_fee) if start.referral_fee is not None else None,
        "grossBillRate": float(start.gross_bill_rate) if start.gross_bill_rate is not None else None,
        "mspFee": float(start.msp_fee) if start.msp_fee is not None else None,
        "margin": float(start.margin) if start.margin is not None else None,
        "remotePosition": start.remote_position,
        "workLocation": start.work_location,
        "candidateLocation": start.candidate_location,
        "workAuthorization": start.work_authorization,
        "resumeSource": start.resume_source,
        "teamLead": start.team_lead,
        "crm": start.crm,
        "teamManager": start.team_manager,
        "headOfDepartment": getattr(start, "head_of_department", None),
        "seniorManager": start.senior_manager,
        "associateDirector": start.associate_director,
        "director": start.director,
        "centerHead": start.center_head,
        "assistantVicePresident": start.assistant_vice_president,
        "onboardingCoordinator": start.onboarding_coordinator,
        "userEmail": start.user_email,
        "recruiterLocation": start.recruiter_location,
        "status": start.status,
    }


def user_audit_snapshot(user: User) -> dict[str, Any]:
    return {
        "fullName": user.full_name,
        "email": user.email,
        "team": user.team_name,
        "isActive": user.is_active,
        "organizationId": user.organization_id,
        "roleId": user.role_id,
    }
