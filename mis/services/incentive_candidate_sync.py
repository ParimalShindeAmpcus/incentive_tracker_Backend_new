"""Sync final-approved MIS starts into the PRISM Candidate Master."""

from datetime import datetime, timezone
from typing import Any

from prism.models.candidates.schemas import CandidateRowIn, CreateVersionRequest


def _normalize_contract_type(value: str | None) -> str:
    raw = (value or "").strip()
    normalized = raw.lower()
    if "w2" in normalized:
        return "W2"
    if "c2c" in normalized or "corp" in normalized:
        return "C2C"
    if "1099" in normalized:
        return "1099"
    if "full" in normalized or "perm" in normalized or "ft" in normalized:
        return "FULLTIME"
    if "inhouse" in normalized or "in-house" in normalized or "internal" in normalized:
        return "INHOUSE"
    if "t4" in normalized:
        return "T4"
    if "sow" in normalized:
        return "SOW"
    return "OTHER"


def candidate_row_from_approved_start(
    start: Any,
    *,
    recruiter_name: str,
    organization_name: str,
) -> CandidateRowIn:
    return CandidateRowIn(
        start_id=str(start.id),
        activity_id=start.activity_id,
        candidate_name=start.candidate_name,
        email=start.candidate_email,
        contact=start.candidate_contact_no,
        client=start.client_name,
        end_client=start.end_client_name,
        job_title=start.job_title,
        start_date=start.start_date,
        end_date=start.end_date,
        req_id=start.req_id,
        contract_type=_normalize_contract_type(start.contract_type),
        subcontractor=start.sub_contractor_company,
        subcontractor_email=start.sub_contractor_email,
        subcontractor_contact=start.sub_contractor_contact,
        job_level=start.job_level,
        salary=start.salary,
        pay_rate=start.pay_rate,
        taxes=start.taxes,
        benefits=start.benefits,
        referral_fee=start.referral_fee,
        bill_rate=start.gross_bill_rate,
        msp_fee=start.msp_fee,
        margin=start.margin,
        remote=(
            "Yes"
            if start.remote_position is True
            else "No"
            if start.remote_position is False
            else None
        ),
        work_location=start.work_location,
        candidate_location=start.candidate_location,
        work_authorization=start.work_authorization,
        resume_source=start.resume_source,
        team_lead=start.team_lead,
        crm=start.crm,
        manager=start.team_manager,
        head_of_department=start.head_of_department,
        senior_manager=start.senior_manager,
        associate_director=start.associate_director,
        director=start.director,
        center_head=start.center_head,
        avp=start.assistant_vice_president,
        onboarding_coordinator=start.onboarding_coordinator,
        user_email=start.user_email,
        recruiter_location=start.recruiter_location,
        recruiter=recruiter_name,
        organization=organization_name,
        status="Approved",
    )


def import_candidate_rows(rows: list[CandidateRowIn]) -> Any:
    from prism.core.db import get_db
    from prism.services.candidates.candidate_service import create_version

    version_label = (
        f"MIS approved starts sync {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    payload = CreateVersionRequest(
        version_label=version_label,
        source_filename="MIS final approved starts",
        notes="Admin-triggered sync from final-approved Starts MIS records.",
        rows=rows,
    )

    session_generator = get_db()
    db = next(session_generator)
    try:
        return create_version(db, payload)
    finally:
        session_generator.close()
