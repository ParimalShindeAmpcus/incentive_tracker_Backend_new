"""VLOOKUP hours reconciliation service (sync Session)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.vlookup.schemas import (
    VLookupActionResponse,
    VLookupMatchesByStatusResponse,
    VLookupRematchBody,
    VLookupReviewBody,
    VLookupStatsResponse,
    VLookupTemplateResponse,
    VLookupTemplateSearchResponse,
    VLookupUploadResponse,
)
from app.repositories.entities.vlookup import (
    VLookupMatchedRecord,
    VLookupTemplateCandidate,
    VLookupUploadBatch,
    VLookupWeeklyHours,
)
from app.repositories.vlookup import vlookup_repository as repo
from app.services.vlookup.normalization import normalize_month_year, normalize_name
from app.services.vlookup.parsers.client_hours import (
    aggregate_hours_by_candidate,
    parse_client_hours_file,
)
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher

logger = logging.getLogger(__name__)


def template_info() -> VLookupTemplateResponse:
    return VLookupTemplateResponse()


def upload_template_and_messy(
    db: Session,
    template_file: UploadFile,
    messy_file: UploadFile,
    target_month: Optional[str] = None,
    uploaded_by: Optional[str] = None,
) -> VLookupUploadResponse:
    batch_id = str(uuid.uuid4())[:8]
    try:
        template_content = template_file.file.read()
        template_df = _parse_tabular_file(template_content, template_file.filename or "template.csv")
        template_df.columns = [
            str(col).lower().strip().replace(" ", "_") for col in template_df.columns
        ]

        required = {"candidate_id", "candidate_name"}
        if not required.issubset(set(template_df.columns)):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Template must include Candidate ID and Candidate Name columns. "
                    f"Found: {list(template_df.columns)}"
                ),
            )

        template_months = [
            normalize_month_year(str(v))
            for v in template_df.get("month", pd.Series(dtype=str)).dropna().unique()
            if str(v).strip() and str(v).lower() != "nan"
        ]
        template_month = template_months[0] if template_months else ""

        template_records: List[VLookupTemplateCandidate] = []
        reused = 0
        created = 0
        # Fast path: insert all template rows for this batch (no per-row DB lookups)
        pending_templates: List[VLookupTemplateCandidate] = []
        for row in template_df.to_dict(orient="records"):
            candidate_id_str = str(row.get("candidate_id", "")).strip()
            if not candidate_id_str or candidate_id_str.lower() == "nan":
                continue
            pending_templates.append(
                VLookupTemplateCandidate(
                    candidate_id=candidate_id_str,
                    candidate_name=str(row.get("candidate_name", "")),
                    client_name=str(row.get("client_name", "") or ""),
                    template_hours=int(
                        float(row.get("hours_worked", row.get("hours", 0)) or 0)
                    ),
                    month=str(row.get("month", template_month or "") or ""),
                    pay_rate=_optional_decimal(row.get("pay_rate")),
                    bill_rate=_optional_decimal(row.get("bill_rate")),
                    margin_per_hour=_optional_decimal(row.get("margin_per_hour")),
                    contract_type=str(row.get("contract_type", "") or ""),
                    division=str(row.get("division", "") or ""),
                    recruiter_name=str(row.get("recruiter_name", "") or ""),
                    team_lead_name=str(row.get("team_lead_name", "") or ""),
                    manager_name=str(row.get("manager_name", "") or ""),
                    crm_name=str(row.get("crm_name", "") or ""),
                    start_date=str(row.get("start_date", "") or ""),
                    end_date=str(row.get("end_date", "") or ""),
                    upload_batch_id=batch_id,
                )
            )
            created += 1

        if pending_templates:
            db.add_all(pending_templates)
            db.flush()
            template_records = pending_templates

        if not template_records:
            raise HTTPException(status_code=400, detail="No valid template candidates found.")

        messy_content = messy_file.file.read()
        unfiltered = parse_client_hours_file(
            messy_content,
            messy_file.filename or "client.csv",
            target_month=None,
        )

        if not unfiltered["rows"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No hours rows could be parsed from the client file. "
                    f"Detected format: {unfiltered.get('format')}. "
                    "Supported: Ampcus QuickBooks (Type/Date/Memo/Name/Qty) or "
                    "flat files with candidate name + hours columns."
                ),
            )

        available_months = unfiltered.get("months_found") or []
        month_filter = _resolve_target_month(
            explicit=target_month,
            template_month=template_month,
            available_months=available_months,
        )

        if month_filter:
            parsed_rows = [
                r
                for r in unfiltered["rows"]
                if normalize_month_year(str(r.get("month") or "")) == month_filter
            ]
        else:
            parsed_rows = list(unfiltered["rows"])

        if not parsed_rows:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No hours data found for the selected month. "
                    f"Detected format: {unfiltered.get('format')}. "
                    f"Requested month: {month_filter or 'none'}. "
                    f"Months available in client file: {available_months}. "
                    "Set Target Month to one of the available months (e.g. 2025-07)."
                ),
            )

        parsed = {
            **unfiltered,
            "rows": parsed_rows,
            "row_count": len(parsed_rows),
            "candidate_count": len({r["candidate_name"] for r in parsed_rows}),
            "target_month": month_filter,
            "months_found": sorted(
                {
                    normalize_month_year(str(r.get("month") or ""))
                    for r in parsed_rows
                    if r.get("month")
                }
            ),
        }

        # Persist ALL weeks across months (bulk insert — much faster than ORM add loops)
        weekly_mappings: List[Dict[str, Any]] = []
        for row in unfiltered["rows"]:
            hours_val = float(row.get("hours_worked") or 0)
            if hours_val <= 0:
                continue
            weekly_mappings.append(
                {
                    "candidate_name_messy": row["candidate_name"],
                    "hours_worked": int(round(hours_val)),
                    "week": str(row.get("week") or "Week"),
                    "month": str(row.get("month") or month_filter or ""),
                    "client_name": str(row.get("client_name") or ""),
                    "normalized_name": row.get("normalized_name")
                    or normalize_name(row["candidate_name"]),
                    "upload_batch_id": batch_id,
                }
            )

        if not weekly_mappings or (
            month_filter
            and not any(
                normalize_month_year(str(r.get("month") or "")) == month_filter
                for r in weekly_mappings
            )
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Client file was parsed but no positive hour rows remained after filtering. "
                    f"Format: {parsed.get('format')}, available months: {available_months}."
                ),
            )

        if weekly_mappings:
            db.bulk_insert_mappings(VLookupWeeklyHours, weekly_mappings)

        client_groups = aggregate_hours_by_candidate(
            parsed["rows"],
            all_rows_for_cumulative=unfiltered["rows"],
        )

        match_month = month_filter or template_month
        template_candidates = [
            {
                "id": r.id,
                "candidate_id": r.candidate_id,
                "candidate_name": r.candidate_name,
                "client_name": r.client_name,
                "month": match_month or r.month,
            }
            for r in template_records
        ]

        matcher = ReconciliationMatcher()
        match_results = matcher.match(
            template_candidates,
            client_groups,
            target_month=match_month or None,
        )

        status_keys = [
            "matched",
            "needs_review",
            "unmatched",
            "potential_duplicate",
            "conflicting",
        ]
        matched_mappings: List[Dict[str, Any]] = []
        for status in status_keys:
            for match in match_results.get(status, []):
                matched_mappings.append(
                    {
                        "template_candidate_id": match.get("template_candidate_id"),
                        "template_candidate_name": match.get("template_candidate_name"),
                        "template_candidate_id_str": match.get("template_candidate_id_str"),
                        "messy_name_original": match.get("messy_name_original"),
                        "messy_client_name": match.get("messy_client_name"),
                        "messy_month": match.get("messy_month") or month_filter,
                        "weekly_hours_ids": [],
                        "weekly_breakdown": match.get("weekly_breakdown") or {},
                        "total_hours": int(match.get("total_hours") or 0),
                        "confidence_score": float(match.get("confidence_score") or 0),
                        "match_status": status,
                        "match_method": match.get("match_method"),
                        "match_explanation": _with_hours_maps(
                            match.get("match_explanation"),
                            weekly_by_month=match.get("weekly_by_month") or {},
                            monthly_hours=match.get("monthly_hours") or {},
                            cumulative_hours=match.get("cumulative_hours"),
                            hours_note=match.get("hours_note") or "",
                        ),
                        "upload_batch_id": batch_id,
                        "manually_reviewed": False,
                    }
                )

        if matched_mappings:
            db.bulk_insert_mappings(VLookupMatchedRecord, matched_mappings)

        messy_count = len(weekly_mappings)

        month_note = None
        if (
            not target_month
            and template_month
            and month_filter
            and template_month != month_filter
        ):
            month_note = (
                f"Template month is {template_month}, but client file has "
                f"{available_months}. Used client month {month_filter} for reconciliation."
            )

        upload_batch = VLookupUploadBatch(
            batch_id=batch_id,
            file_type="template_and_messy",
            filename=f"{template_file.filename} + {messy_file.filename}",
            total_records=len(template_records) + messy_count,
            status="completed",
            matched_count=len(match_results.get("matched", [])),
            needs_review_count=len(match_results.get("needs_review", [])),
            unmatched_count=len(match_results.get("unmatched", [])),
            duplicate_count=len(match_results.get("potential_duplicate", [])),
            conflicting_count=len(match_results.get("conflicting", [])),
            target_month=month_filter or None,
            client_file_format=parsed.get("format"),
            parser_warnings=(parsed.get("warnings") or []) + ([month_note] if month_note else []),
            uploaded_by=uploaded_by or "system",
            completed_at=datetime.utcnow(),
        )
        db.add(upload_batch)
        db.commit()

        return VLookupUploadResponse(
            status="success",
            batch_id=batch_id,
            target_month=month_filter or None,
            template_month=template_month or None,
            client_file_format=parsed.get("format"),
            template_count=len(template_records),
            template_created=created,
            template_reused=reused,
            messy_count=messy_count,            client_candidate_count=parsed.get("candidate_count"),
            months_in_client_file=list(available_months),
            matched_count=len(match_results.get("matched", [])),
            needs_review_count=len(match_results.get("needs_review", [])),
            unmatched_count=len(match_results.get("unmatched", [])),
            duplicate_count=len(match_results.get("potential_duplicate", [])),
            conflicting_count=len(match_results.get("conflicting", [])),
            parser_warnings=(parsed.get("warnings") or []) + ([month_note] if month_note else []),
            month_note=month_note,
            total_records=(
                len(match_results.get("matched", []))
                + len(match_results.get("needs_review", []))
                + len(match_results.get("unmatched", []))
                + len(match_results.get("potential_duplicate", []))
                + len(match_results.get("conflicting", []))
            ),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("VLOOKUP upload failed")
        detail = str(exc)
        if "UnicodeDecodeError" in detail or "codec" in detail:
            detail = "File encoding error. Save CSV as UTF-8 or use Excel (.xlsx)."
        raise HTTPException(status_code=500, detail=f"Upload failed: {detail}") from exc


def get_stats(db: Session, batch_id: Optional[str] = None) -> VLookupStatsResponse:
    latest = repo.latest_batch_id(db, batch_id)
    if not latest:
        return VLookupStatsResponse()

    counts = {status: repo.count_by_status(db, latest, status) for status in repo.VALID_STATUSES}
    batch = repo.get_batch(db, latest)
    return VLookupStatsResponse(
        batch_id=latest,
        matched_count=counts["matched"],
        needs_review_count=counts["needs_review"],
        unmatched_count=counts["unmatched"],
        duplicate_count=counts["potential_duplicate"],
        conflicting_count=counts["conflicting"],
        total_records=sum(counts.values()),
        unique_master_candidates=repo.count_unique_master_candidates(db, latest),
        target_month=batch.target_month if batch else None,
        client_file_format=batch.client_file_format if batch else None,
        parser_warnings=list(batch.parser_warnings or []) if batch else [],
    )


def get_matches_by_status(
    db: Session, status: str, batch_id: Optional[str] = None
) -> VLookupMatchesByStatusResponse:
    if status not in repo.VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {sorted(repo.VALID_STATUSES)}",
        )
    latest = repo.latest_batch_id(db, batch_id)
    if not latest:
        return VLookupMatchesByStatusResponse(status=status, batch_id=None, matches=[])

    matches = repo.list_matches_by_status(db, latest, status)
    out = []
    for match in matches:
        template = None
        if match.template_candidate_id:
            template = repo.get_template_by_id(db, match.template_candidate_id)
        payload = repo.serialize_match(match, template)
        weekly_by_month = payload.get("weekly_by_month") or {}
        if not weekly_by_month:
            weekly_by_month = _rebuild_weekly_by_month(
                db, latest, match.messy_name_original
            )
            payload["weekly_by_month"] = weekly_by_month
            # Also expose on explanation for clients that read nested fields
            explanation = dict(payload.get("match_explanation") or {})
            explanation["weekly_by_month"] = weekly_by_month
            payload["match_explanation"] = explanation
        out.append(payload)
    return VLookupMatchesByStatusResponse(status=status, batch_id=latest, matches=out)


def search_template_candidates(
    db: Session,
    q: Optional[str] = None,
    client: Optional[str] = None,
    batch_id: Optional[str] = None,
    limit: int = 25,
) -> VLookupTemplateSearchResponse:
    latest = repo.latest_batch_id(db, batch_id)
    rows = repo.list_templates_for_batch(db, latest)
    templates = [
        {
            "id": r.id,
            "candidate_id": r.candidate_id,
            "candidate_name": r.candidate_name,
            "client_name": r.client_name,
            "month": r.month,
        }
        for r in rows
    ]

    messy_name = (q or "").strip()
    if not messy_name:
        return VLookupTemplateSearchResponse(
            candidates=[
                {
                    "id": t["id"],
                    "candidate_id": t["candidate_id"],
                    "candidate_name": t["candidate_name"],
                    "client_name": t["client_name"],
                    "month": t["month"],
                    "why_suggested": "",
                    "identity_compatible": False,
                    "confidence": 0,
                }
                for t in templates[:limit]
            ]
        )

    matcher = ReconciliationMatcher()
    ranked = matcher.rank_for_rematch(
        messy_name=messy_name,
        template_candidates=templates,
        messy_client=client,
        limit=limit,
    )
    if not ranked:
        like = messy_name.lower()
        ranked = [
            {
                "id": t["id"],
                "candidate_id": t["candidate_id"],
                "candidate_name": t["candidate_name"],
                "client_name": t["client_name"],
                "month": t["month"],
                "why_suggested": "Text contains search tokens",
                "identity_compatible": False,
                "confidence": 0,
            }
            for t in templates
            if like in (t["candidate_name"] or "").lower()
            or like in (t["candidate_id"] or "").lower()
        ][:limit]

    return VLookupTemplateSearchResponse(candidates=ranked)


def accept_match(
    db: Session, match_id: int, body: Optional[VLookupReviewBody] = None
) -> VLookupActionResponse:
    match = repo.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if not match.template_candidate_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot accept unmatched record without a template candidate. Use rematch first.",
        )

    body = body or VLookupReviewBody()
    match.match_status = "matched"
    match.review_action = "accepted"
    repo.touch_reviewed(match, reviewed_by=body.reviewed_by, notes=body.notes)

    explanation = dict(match.match_explanation or {})
    summary = (
        f"Accepted: Accounts confirmed identity as '{match.template_candidate_name}' "
        f"for source '{match.messy_name_original}'."
    )
    if body.notes:
        summary = f"{summary} Note: {body.notes}"
    explanation["identity_summary"] = summary
    explanation["identity_headline"] = f"Matched: {match.template_candidate_name}"
    explanation["audit"] = {
        "what_happened": explanation["identity_headline"],
        "why": summary,
        "identity_status": "matched",
        "validation_status": (explanation.get("validation") or {}).get("status"),
        "validation_summary": (explanation.get("validation") or {}).get("summary"),
        "has_alternatives": bool(explanation.get("alternatives")),
    }
    match.match_explanation = explanation
    db.commit()
    return VLookupActionResponse(match_id=match_id, message="Match accepted")


def reject_match(
    db: Session, match_id: int, body: Optional[VLookupReviewBody] = None
) -> VLookupActionResponse:
    match = repo.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    body = body or VLookupReviewBody()
    previous_name = match.template_candidate_name
    match.match_status = "unmatched"
    match.review_action = "rejected"
    match.template_candidate_id = None
    match.template_candidate_name = None
    match.template_candidate_id_str = None
    match.confidence_score = 0.0
    match.match_method = "manual_reject"
    repo.touch_reviewed(match, reviewed_by=body.reviewed_by, notes=body.notes)

    explanation = dict(match.match_explanation or {})
    rejected_name = f" '{previous_name}'" if previous_name else ""
    summary = (
        f"Rejected: Accounts rejected suggested identity{rejected_name} "
        f"for source '{match.messy_name_original}'."
    )
    if body.notes:
        summary = f"{summary} Note: {body.notes}"
    explanation["identity_summary"] = summary
    explanation["identity_headline"] = "Unmatched (rejected)"
    explanation["alternatives"] = explanation.get("alternatives") or []
    explanation["audit"] = {
        "what_happened": explanation["identity_headline"],
        "why": summary,
        "identity_status": "unmatched",
        "validation_status": (explanation.get("validation") or {}).get("status"),
        "validation_summary": (explanation.get("validation") or {}).get("summary"),
        "has_alternatives": bool(explanation.get("alternatives")),
    }
    match.match_explanation = explanation
    db.commit()
    return VLookupActionResponse(match_id=match_id, message="Match rejected")


def rematch(
    db: Session, match_id: int, body: VLookupRematchBody
) -> VLookupActionResponse:
    match = repo.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    template = repo.get_template_by_id(db, body.template_candidate_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template candidate not found")

    match.template_candidate_id = template.id
    match.template_candidate_name = template.candidate_name
    match.template_candidate_id_str = template.candidate_id
    match.match_method = "manual"
    match.review_action = "modified"
    match.confidence_score = 100.0
    match.match_status = "matched" if body.accept else "needs_review"
    repo.touch_reviewed(match, reviewed_by=body.reviewed_by, notes=body.notes)

    explanation = dict(match.match_explanation or {})
    summary = (
        f"Rematched: user selected '{template.candidate_name}' "
        f"({template.candidate_id}) for source '{match.messy_name_original}'."
    )
    if body.notes:
        summary = f"{summary} Note: {body.notes}"
    explanation["identity_summary"] = summary
    explanation["identity_headline"] = f"Rematched: {template.candidate_name}"
    explanation["manual_selection"] = {
        "candidate_id": template.candidate_id,
        "candidate_name": template.candidate_name,
        "client_name": template.client_name,
        "reviewed_by": body.reviewed_by,
        "notes": body.notes,
    }
    explanation["alternatives"] = []
    explanation["audit"] = {
        "what_happened": explanation["identity_headline"],
        "why": summary,
        "identity_status": match.match_status,
        "validation_status": (explanation.get("validation") or {}).get("status"),
        "validation_summary": (explanation.get("validation") or {}).get("summary"),
        "has_alternatives": False,
    }
    match.match_explanation = explanation
    db.commit()
    return VLookupActionResponse(
        match_id=match_id,
        message="Match updated",
        template_candidate_id=template.candidate_id,
        template_candidate_name=template.candidate_name,
    )


def download_matches(
    db: Session,
    batch_id: Optional[str] = None,
    include_review_pending: bool = False,
) -> StreamingResponse:
    latest = repo.latest_batch_id(db, batch_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No matches found")

    statuses = ["matched"]
    if include_review_pending:
        statuses.append("needs_review")

    matches = repo.list_matches_for_download(db, latest, statuses)
    data = []
    for match in matches:
        if not match.template_candidate_id:
            continue
        template = repo.get_template_by_id(db, match.template_candidate_id)
        month_value = (
            (template.month if template and template.month else None)
            or match.messy_month
            or ""
        )
        explanation = match.match_explanation or {}
        data.append(
            {
                "Candidate ID": match.template_candidate_id_str or "",
                "Candidate Name": match.template_candidate_name or "",
                "Client Name": template.client_name if template else "",
                "Hours Worked": match.total_hours,
                "Month": month_value,
                "Match Status": match.match_status,
                "Confidence": match.confidence_score,
                "Client Name (Source)": match.messy_client_name or "",
                "Source Name": match.messy_name_original or "",
                "Cumulative Hours (Client File)": explanation.get("cumulative_hours"),
                "Hours Note": explanation.get("hours_note") or "",
            }
        )

    df = pd.DataFrame(data)
    export_cols = [
        "Candidate ID",
        "Candidate Name",
        "Client Name",
        "Hours Worked",
        "Month",
    ]
    audit_cols = export_cols + [
        "Match Status",
        "Confidence",
        "Client Name (Source)",
        "Source Name",
        "Cumulative Hours (Client File)",
        "Hours Note",
    ]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        (df[export_cols] if not df.empty else pd.DataFrame(columns=export_cols)).to_excel(
            writer, sheet_name="Hours Template", index=False
        )
        (df[audit_cols] if not df.empty else pd.DataFrame(columns=audit_cols)).to_excel(
            writer, sheet_name="Audit Detail", index=False
        )
    output.seek(0)

    filename = f"hours_reconciled_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _optional_decimal(value: Any):
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        return float(text)
    except Exception:
        return None


def _with_hours_maps(
    explanation: Optional[Dict[str, Any]],
    *,
    weekly_by_month: Optional[Dict[str, Any]] = None,
    monthly_hours: Optional[Dict[str, Any]] = None,
    cumulative_hours: Any = None,
    hours_note: str = "",
) -> Dict[str, Any]:
    """Ensure hours maps are always persisted inside match_explanation JSON."""
    out = dict(explanation or {})
    if weekly_by_month is not None:
        out["weekly_by_month"] = weekly_by_month
    if monthly_hours is not None:
        out["monthly_hours"] = monthly_hours
    if cumulative_hours is not None:
        out["cumulative_hours"] = cumulative_hours
    if hours_note:
        out["hours_note"] = hours_note
    return out


def _rebuild_weekly_by_month(
    db: Session,
    batch_id: str,
    messy_name: Optional[str],
) -> Dict[str, Dict[str, float]]:
    """Rebuild per-month weekly map from stored weekly hours for this person/batch."""
    if not messy_name or not batch_id:
        return {}
    nkey = normalize_name(messy_name)
    rows = (
        db.query(VLookupWeeklyHours)
        .filter(VLookupWeeklyHours.upload_batch_id == batch_id)
        .filter(
            (VLookupWeeklyHours.normalized_name == nkey)
            | (VLookupWeeklyHours.candidate_name_messy == messy_name)
        )
        .all()
    )
    # Broader fallback: same normalized name family in batch
    if not rows:
        rows = (
            db.query(VLookupWeeklyHours)
            .filter(VLookupWeeklyHours.upload_batch_id == batch_id)
            .filter(VLookupWeeklyHours.normalized_name == nkey)
            .all()
        )
    by_month: Dict[str, Dict[str, float]] = {}
    for row in rows:
        # Keep only rows whose name normalizes to the same key (variants)
        if normalize_name(row.candidate_name_messy or "") != nkey and (row.normalized_name or "") != nkey:
            continue
        month = normalize_month_year(str(row.month or "")) or "unknown"
        week = str(row.week or "Week")
        by_month.setdefault(month, {})
        by_month[month][week] = float(by_month[month].get(week, 0) + float(row.hours_worked or 0))
    return by_month


def _resolve_target_month(
    explicit: Optional[str],
    template_month: str,
    available_months: list,
) -> Optional[str]:
    if explicit:
        return normalize_month_year(explicit)

    normalized_available = [normalize_month_year(m) for m in available_months if m]
    if template_month and template_month in normalized_available:
        return template_month

    if normalized_available:
        return sorted(normalized_available)[-1]

    return normalize_month_year(template_month) if template_month else None


def _parse_tabular_file(file_content: bytes, filename: str) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith(".csv"):
        for encoding in ("utf-8", "utf-8-sig", "latin-1", "iso-8859-1", "cp1252"):
            try:
                return pd.read_csv(BytesIO(file_content), encoding=encoding)
            except Exception:
                continue
        raise ValueError("Failed to decode CSV file with supported encodings")
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(file_content))
    raise ValueError(f"Unsupported file format: {filename}")
