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
            "client_name": template.client_name if template else None,
            "month": template.month if template else None,
            "recruiter_name": template.recruiter_name if template else None,
            "pay_rate": float(template.pay_rate) if template and template.pay_rate else None,
            "bill_rate": float(template.bill_rate) if template and template.bill_rate else None,
        }
        if template
        else {
            "client_name": None,
            "month": match.messy_month,
            "recruiter_name": None,
            "pay_rate": None,
            "bill_rate": None,
        },
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
