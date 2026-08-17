"""Persistence helpers for VLOOKUP reconciliation tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.repositories.entities.vlookup import (
    VLookupMatchedRecord,
    VLookupTemplateCandidate,
    VLookupUploadBatch,
    VLookupWeeklyHours,
)

VALID_STATUSES = {
    "matched",
    "needs_review",
    "unmatched",
    "potential_duplicate",
    "conflicting",
    "accepted",
    "rejected",
}


def latest_batch_id(db: Session, batch_id: Optional[str] = None) -> Optional[str]:
    if batch_id:
        return batch_id
    row = db.execute(
        select(VLookupUploadBatch.batch_id)
        .order_by(desc(VLookupUploadBatch.created_at), desc(VLookupUploadBatch.id))
        .limit(1)
    ).scalar_one_or_none()
    return row


def get_batch(db: Session, batch_id: str) -> Optional[VLookupUploadBatch]:
    return db.execute(
        select(VLookupUploadBatch).where(VLookupUploadBatch.batch_id == batch_id)
    ).scalar_one_or_none()


def get_template_by_candidate_id(
    db: Session, candidate_id: str
) -> Optional[VLookupTemplateCandidate]:
    return db.execute(
        select(VLookupTemplateCandidate).where(
            VLookupTemplateCandidate.candidate_id == candidate_id
        )
    ).scalar_one_or_none()


def get_template_by_id(db: Session, template_id: int) -> Optional[VLookupTemplateCandidate]:
    return db.execute(
        select(VLookupTemplateCandidate).where(VLookupTemplateCandidate.id == template_id)
    ).scalar_one_or_none()


def list_templates_for_batch(
    db: Session, batch_id: Optional[str]
) -> List[VLookupTemplateCandidate]:
    stmt = select(VLookupTemplateCandidate)
    if batch_id:
        stmt = stmt.where(VLookupTemplateCandidate.upload_batch_id == batch_id)
    rows = list(db.execute(stmt).scalars().all())
    if rows or not batch_id:
        return rows
    return list(db.execute(select(VLookupTemplateCandidate)).scalars().all())


def get_match(db: Session, match_id: int) -> Optional[VLookupMatchedRecord]:
    return db.execute(
        select(VLookupMatchedRecord).where(VLookupMatchedRecord.id == match_id)
    ).scalar_one_or_none()


def list_matches_by_status(
    db: Session, batch_id: str, status: str
) -> List[VLookupMatchedRecord]:
    return list(
        db.execute(
            select(VLookupMatchedRecord)
            .where(VLookupMatchedRecord.upload_batch_id == batch_id)
            .where(VLookupMatchedRecord.match_status == status)
            .order_by(VLookupMatchedRecord.confidence_score.desc())
        ).scalars().all()
    )


def count_by_status(db: Session, batch_id: str, status: str) -> int:
    return (
        db.execute(
            select(func.count(VLookupMatchedRecord.id))
            .where(VLookupMatchedRecord.upload_batch_id == batch_id)
            .where(VLookupMatchedRecord.match_status == status)
        ).scalar()
        or 0
    )


def count_unique_master_candidates(db: Session, batch_id: str) -> int:
    """Distinct Hours Template candidates that linked to a client-file identity."""
    return (
        db.execute(
            select(func.count(func.distinct(VLookupMatchedRecord.template_candidate_id)))
            .where(VLookupMatchedRecord.upload_batch_id == batch_id)
            .where(VLookupMatchedRecord.template_candidate_id.isnot(None))
            .where(VLookupMatchedRecord.messy_name_original.isnot(None))
            .where(VLookupMatchedRecord.match_status != "rejected")
        ).scalar()
        or 0
    )


def count_template_candidates(db: Session, batch_id: str) -> int:
    return (
        db.execute(
            select(func.count(VLookupTemplateCandidate.id)).where(
                VLookupTemplateCandidate.upload_batch_id == batch_id
            )
        ).scalar()
        or 0
    )


def list_weekly_hours_for_batch(
    db: Session, batch_id: Optional[str]
) -> List[VLookupWeeklyHours]:
    if not batch_id:
        return []
    return list(
        db.execute(
            select(VLookupWeeklyHours)
            .where(VLookupWeeklyHours.upload_batch_id == batch_id)
            .order_by(VLookupWeeklyHours.candidate_name_messy, VLookupWeeklyHours.month)
        ).scalars().all()
    )


def list_months_for_batch(db: Session, batch_id: str) -> List[str]:
    rows = db.execute(
        select(VLookupWeeklyHours.month)
        .where(VLookupWeeklyHours.upload_batch_id == batch_id)
        .where(VLookupWeeklyHours.month.isnot(None))
        .distinct()
    ).scalars().all()
    months = sorted({str(m) for m in rows if m})
    return months


def list_matches_for_download(
    db: Session, batch_id: str, statuses: Sequence[str]
) -> List[VLookupMatchedRecord]:
    return list(
        db.execute(
            select(VLookupMatchedRecord)
            .where(VLookupMatchedRecord.upload_batch_id == batch_id)
            .where(VLookupMatchedRecord.match_status.in_(list(statuses)))
            .order_by(VLookupMatchedRecord.template_candidate_name)
        ).scalars().all()
    )


def add_weekly_hours(db: Session, rows: List[VLookupWeeklyHours]) -> None:
    for row in rows:
        db.add(row)


def add_matched_records(db: Session, rows: List[VLookupMatchedRecord]) -> None:
    for row in rows:
        db.add(row)


def add_batch(db: Session, batch: VLookupUploadBatch) -> VLookupUploadBatch:
    db.add(batch)
    return batch


def serialize_match(
    match: VLookupMatchedRecord, template: Optional[VLookupTemplateCandidate] = None
) -> Dict[str, Any]:
    explanation = match.match_explanation or {}
    audit = explanation.get("audit") or {}
    validation = explanation.get("validation") or {}
    alternatives = explanation.get("alternatives") or []
    return {
        "id": match.id,
        "batch_id": match.upload_batch_id,
        "template_candidate_id": match.template_candidate_id,
        "template_candidate_name": match.template_candidate_name,
        "template_candidate_id_str": match.template_candidate_id_str,
        "messy_name_original": match.messy_name_original,
        "messy_client_name": match.messy_client_name,
        "messy_month": match.messy_month,
        "total_hours": match.total_hours,
        "cumulative_hours": explanation.get("cumulative_hours"),
        "monthly_hours": explanation.get("monthly_hours") or {},
        "weekly_by_month": explanation.get("weekly_by_month") or {},
        "hours_note": explanation.get("hours_note") or "",
        "weekly_breakdown": match.weekly_breakdown,
        "confidence_score": float(match.confidence_score or 0),
        "match_status": match.match_status,
        "identity_status": match.match_status,
        "validation_status": validation.get("status") or explanation.get("validation_status"),
        "validation_summary": validation.get("summary") or "",
        "match_method": match.match_method,
        "match_explanation": explanation,
        "identity_summary": explanation.get("identity_summary") or audit.get("why") or "",
        "identity_headline": explanation.get("identity_headline") or audit.get("what_happened") or "",
        "audit": audit,
        "alternatives": alternatives,
        "manually_reviewed": match.manually_reviewed,
        "review_action": match.review_action,
        "review_notes": match.review_notes,
        "template_details": {
            "candidate_id": template.candidate_id if template else match.template_candidate_id_str,
            "candidate_name": template.candidate_name if template else match.template_candidate_name,
            "client_name": template.client_name if template else None,
            "month": template.month if template else None,
            "hours_worked": template.template_hours if template else None,
            "recruiter_name": template.recruiter_name if template else None,
            "team_lead_name": template.team_lead_name if template else None,
            "manager_name": template.manager_name if template else None,
            "crm_name": template.crm_name if template else None,
            "division": template.division if template else None,
            "contract_type": template.contract_type if template else None,
            "start_date": template.start_date if template else None,
            "end_date": template.end_date if template else None,
            "pay_rate": float(template.pay_rate) if template and template.pay_rate else None,
            "bill_rate": float(template.bill_rate) if template and template.bill_rate else None,
            "margin_per_hour": float(template.margin_per_hour) if template and template.margin_per_hour else None,
        }
        if template
        else {
            "candidate_id": match.template_candidate_id_str,
            "candidate_name": match.template_candidate_name,
            "client_name": None,
            "month": match.messy_month,
            "hours_worked": None,
            "recruiter_name": None,
            "team_lead_name": None,
            "manager_name": None,
            "crm_name": None,
            "division": None,
            "contract_type": None,
            "start_date": None,
            "end_date": None,
            "pay_rate": None,
            "bill_rate": None,
            "margin_per_hour": None,
        },
    }


def serialize_template_candidate(row: VLookupTemplateCandidate) -> Dict[str, Any]:
    return {
        "id": row.id,
        "candidate_id": row.candidate_id,
        "candidate_name": row.candidate_name,
        "client_name": row.client_name,
        "month": row.month,
        "hours_worked": row.template_hours,
        "recruiter_name": row.recruiter_name,
        "team_lead_name": row.team_lead_name,
        "manager_name": row.manager_name,
        "crm_name": row.crm_name,
        "division": row.division,
        "contract_type": row.contract_type,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "pay_rate": float(row.pay_rate) if row.pay_rate is not None else None,
        "bill_rate": float(row.bill_rate) if row.bill_rate is not None else None,
        "margin_per_hour": float(row.margin_per_hour) if row.margin_per_hour is not None else None,
    }


def touch_reviewed(
    match: VLookupMatchedRecord,
    *,
    reviewed_by: Optional[str],
    notes: Optional[str],
) -> None:
    match.manually_reviewed = True
    match.reviewed_by = reviewed_by
    match.review_notes = notes
    match.reviewed_at = datetime.utcnow()
