"""VLOOKUP hours reconciliation service (sync Session)."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.hours.schemas import CreateHoursVersionRequest, HoursRowIn
from app.models.vlookup.schemas import (
    VLookupActionResponse,
    VLookupCancelBody,
    VLookupDraftListResponse,
    VLookupDraftOut,
    VLookupMatchesByStatusResponse,
    VLookupPublishHoursResponse,
    VLookupRematchBody,
    VLookupReviewBody,
    VLookupStatsResponse,
    VLookupTemplateResponse,
    VLookupTemplateSearchResponse,
    VLookupUploadResponse,
)
from app.repositories.audit import audit_repository
from app.repositories.entities.audit import AuditAction
from app.repositories.entities.user import User
from app.repositories.entities.vlookup import (
    VLookupMatchedRecord,
    VLookupTemplateCandidate,
    VLookupUploadBatch,
    VLookupWeeklyHours,
)
from app.repositories.vlookup import vlookup_repository as repo
from app.repositories.candidates import candidate_repository
from app.services.audit import audit_service
from app.services.hours import hours_service
from app.services.vlookup.normalization import normalize_month_year, normalize_name
from app.services.vlookup.parsers.client_hours import (
    aggregate_hours_by_candidate,
    parse_client_hours_file,
)
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher

logger = logging.getLogger(__name__)


def _candidate_lookup_keys(candidate) -> List[str]:
    keys: List[str] = []
    for value in (
        getattr(candidate, "external_candidate_id", None),
        getattr(candidate, "start_id", None),
        getattr(candidate, "activity_id", None),
    ):
        key = str(value or "").strip().lower()
        if key:
            keys.append(key)
    return keys


def _restrict_templates_to_nashik_division(
    db: Session,
    templates: List[VLookupTemplateCandidate],
) -> Tuple[List[VLookupTemplateCandidate], int]:
    """Keep Hours Template rows that belong to Nashik (Organisation + Recruiter Location).

    Rows that cannot be found in Candidate Master are kept so matching tests and
    ad-hoc IDs still work. Known non-Nashik master records are excluded.
    """
    from app.services.incentives.nashik_rules import is_nashik_hours_scope

    masters = candidate_repository.list_all_candidates(db)
    if not masters:
        return templates, 0

    by_id: Dict[str, Any] = {}
    for master in masters:
        for key in _candidate_lookup_keys(master):
            by_id.setdefault(key, master)

    kept: List[VLookupTemplateCandidate] = []
    skipped = 0
    for template in templates:
        cid = str(getattr(template, "candidate_id", "") or "").strip().lower()
        master = by_id.get(cid)
        if master is None:
            kept.append(template)
            continue
        if is_nashik_hours_scope(
            organization=master.organization,
            candidate_source=master.candidate_source,
            recruiter_location=master.recruiter_location,
        ):
            kept.append(template)
        else:
            skipped += 1
    return kept, skipped


def template_info() -> VLookupTemplateResponse:
    return VLookupTemplateResponse()


def upload_template_and_messy(
    db: Session,
    template_file: UploadFile,
    messy_file: UploadFile,
    target_month: Optional[str] = None,
    uploaded_by: Optional[str] = None,
    user: Optional[User] = None,
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

        template_months = sorted(
            {
                normalize_month_year(str(v))
                for v in template_df.get("month", pd.Series(dtype=str)).dropna().unique()
                if str(v).strip()
                and str(v).lower() != "nan"
                and normalize_month_year(str(v))
            }
        )
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
                    month=normalize_month_year(str(row.get("month", "") or ""))
                    or template_month
                    or "",
                    contract_type=str(row.get("contract_type", "") or ""),
                    division=str(row.get("division", "") or ""),
                    recruiter_name=str(row.get("recruiter_name", "") or ""),
                    upload_batch_id=batch_id,
                )
            )
            created += 1

        nashik_scope_note = None
        pending_templates, skipped_non_nashik = _restrict_templates_to_nashik_division(
            db, pending_templates
        )
        created = len(pending_templates)
        if skipped_non_nashik:
            nashik_scope_note = (
                "Smart Match is limited to the Nashik division. "
                f"{skipped_non_nashik} Hours Template row(s) belonging to other divisions "
                "(identified from Organisation and Recruiter Location) were excluded."
            )

        if pending_templates:
            db.add_all(pending_templates)
            db.flush()
            template_records = pending_templates

        if not template_records:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No Nashik division candidates found in the Hours Template. "
                    "Smart Match only processes candidates whose Organisation and "
                    "Recruiter Location belong to Nashik."
                    if skipped_non_nashik
                    else "No valid template candidates found."
                ),
            )

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
            template_months=template_months,
            available_months=available_months,
        )

        # Keep every month in the client file. Identity is matched once;
        # Accounts pick a month on the results dashboard for display/export.
        parsed_rows = list(unfiltered["rows"])
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

        if not weekly_mappings:
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
            group_by_month=False,
        )

        match_month = month_filter or template_month
        template_candidates = [
            {
                "id": r.id,
                "candidate_id": r.candidate_id,
                "candidate_name": r.candidate_name,
                "client_name": r.client_name,
                "month": normalize_month_year(str(r.month or "")) or "",
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
            "accepted",
            "rejected",
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
        client_months_norm = [normalize_month_year(m) for m in (available_months or []) if m]
        overlap_months = [m for m in template_months if m in client_months_norm]
        if available_months:
            months_label = ", ".join(available_months)
            template_label = ", ".join(template_months) if template_months else "none"
            if overlap_months:
                month_note = (
                    f"Client file contains {len(available_months)} month(s): {months_label}. "
                    f"Hours Template month(s): {template_label}. "
                    "People are matched by identity when the year overlaps. "
                    "Hours for the selected month are taken from the client file "
                    "(0 if that person has no weeks in that month)."
                )
            else:
                template_years = {m[:4] for m in template_months if m}
                client_years = {m[:4] for m in client_months_norm if m}
                if template_years and client_years and template_years.isdisjoint(client_years):
                    month_note = (
                        f"Hours Template year(s) {', '.join(sorted(template_years))} do not "
                        f"overlap client file year(s) {', '.join(sorted(client_years))}. "
                        "Auto-match requires the same year."
                    )
                else:
                    month_note = (
                        f"Client file contains {len(available_months)} month(s): {months_label}. "
                        f"Hours Template month(s): {template_label}. "
                        "People are matched by identity. Hours for a month are 0 when that "
                        "person has no client-file weeks in that month."
                    )
            if target_month and month_filter:
                month_note += f" Default month filter: {month_filter}."
        elif template_month:
            month_note = f"No month could be detected in the client file. Template month is {template_month}."

        parser_warnings = (
            (parsed.get("warnings") or [])
            + ([month_note] if month_note else [])
            + ([nashik_scope_note] if nashik_scope_note else [])
        )

        upload_batch = VLookupUploadBatch(
            batch_id=batch_id,
            file_type="template_and_messy",
            filename=f"{template_file.filename} + {messy_file.filename}",
            total_records=len(template_records) + messy_count,
            status="running",
            stage="review",
            matched_count=len(match_results.get("matched", [])),
            needs_review_count=len(match_results.get("needs_review", [])),
            unmatched_count=len(match_results.get("unmatched", [])),
            duplicate_count=len(match_results.get("potential_duplicate", [])),
            conflicting_count=len(match_results.get("conflicting", [])),
            target_month=month_filter or None,
            client_file_format=parsed.get("format"),
            parser_warnings=parser_warnings,
            uploaded_by=uploaded_by or "system",
            completed_at=datetime.utcnow(),
        )
        db.add(upload_batch)
        audit_service.record_event(
            db,
            action=AuditAction.FILE_UPLOAD,
            title="Uploaded VLOOKUP files",
            details=(
                f"Uploaded {template_file.filename} and {messy_file.filename}: "
                f"{len(match_results.get('matched', []))} matched, "
                f"{len(match_results.get('unmatched', []))} unmatched"
            ),
            user=user,
            metadata={
                "batch_id": batch_id,
                "template_filename": template_file.filename,
                "messy_filename": messy_file.filename,
                "matched_count": len(match_results.get("matched", [])),
                "unmatched_count": len(match_results.get("unmatched", [])),
                "target_month": month_filter or None,
            },
            entity_type="vlookup_batch",
            entity_id=batch_id,
        )
        audit_service.record_event(
            db,
            action=AuditAction.HOURS_RECONCILIATION,
            title="VLOOKUP reconciliation completed",
            details=(
                f"Matched {len(match_results.get('matched', []))} of "
                f"{len(template_records)} template candidate(s) from {messy_file.filename}"
            ),
            user=user,
            metadata={
                "batch_id": batch_id,
                "matched_count": len(match_results.get("matched", [])),
                "unmatched_count": len(match_results.get("unmatched", [])),
                "needs_review_count": len(match_results.get("needs_review", [])),
                "target_month": month_filter or None,
            },
            entity_type="vlookup_batch",
            entity_id=batch_id,
        )
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
            messy_count=messy_count,
            client_candidate_count=parsed.get("candidate_count"),
            months_in_client_file=list(available_months),
            matched_count=len(match_results.get("matched", [])),
            needs_review_count=len(match_results.get("needs_review", [])),
            unmatched_count=len(match_results.get("unmatched", [])),
            duplicate_count=len(match_results.get("potential_duplicate", [])),
            conflicting_count=len(match_results.get("conflicting", [])),
            accepted_count=len(match_results.get("accepted", [])),
            rejected_count=len(match_results.get("rejected", [])),
            parser_warnings=parser_warnings,
            month_note=month_note,
            total_records=(
                len(match_results.get("matched", []))
                + len(match_results.get("needs_review", []))
                + len(match_results.get("unmatched", []))
                + len(match_results.get("potential_duplicate", []))
                + len(match_results.get("conflicting", []))
                + len(match_results.get("accepted", []))
                + len(match_results.get("rejected", []))
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


def get_stats(
    db: Session, batch_id: Optional[str] = None, month: Optional[str] = None
) -> VLookupStatsResponse:
    latest = repo.latest_batch_id(db, batch_id)
    if not latest:
        return VLookupStatsResponse()

    month_key = normalize_month_year(str(month or "")) or None
    counts = {
        status: repo.count_by_status(db, latest, status, month_key=month_key)
        for status in repo.VALID_STATUSES
    }
    batch = repo.get_batch(db, latest)
    return VLookupStatsResponse(
        batch_id=latest,
        matched_count=counts.get("matched", 0),
        needs_review_count=counts.get("needs_review", 0),
        unmatched_count=counts.get("unmatched", 0),
        duplicate_count=counts.get("potential_duplicate", 0),
        conflicting_count=counts.get("conflicting", 0),
        accepted_count=counts.get("accepted", 0),
        rejected_count=counts.get("rejected", 0),
        total_records=sum(counts.values()),
        unique_master_candidates=repo.count_unique_master_candidates(
            db, latest, month_key=month_key
        ),
        hours_template_count=repo.count_template_candidates(
            db, latest, month_key=month_key
        ),
        target_month=batch.target_month if batch else None,
        client_file_format=batch.client_file_format if batch else None,
        parser_warnings=list(batch.parser_warnings or []) if batch else [],
        months_in_client_file=repo.list_months_for_batch(db, latest),
    )


def get_matches_by_status(
    db: Session,
    status: str,
    batch_id: Optional[str] = None,
    month: Optional[str] = None,
) -> VLookupMatchesByStatusResponse:
    if status not in repo.VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {sorted(repo.VALID_STATUSES)}",
        )
    latest = repo.latest_batch_id(db, batch_id)
    if not latest:
        return VLookupMatchesByStatusResponse(status=status, batch_id=None, matches=[])

    month_key = normalize_month_year(str(month or "")) or None
    matches = repo.list_matches_by_status(db, latest, status, month_key=month_key)
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
        monthly_hours = payload.get("monthly_hours") or {}
        if (not monthly_hours) and weekly_by_month:
            monthly_hours = {
                month: float(sum(float(h or 0) for h in (weeks or {}).values()))
                for month, weeks in weekly_by_month.items()
            }
            payload["monthly_hours"] = monthly_hours
        if weekly_by_month or monthly_hours:
            explanation = dict(payload.get("match_explanation") or {})
            if weekly_by_month:
                explanation["weekly_by_month"] = weekly_by_month
            if monthly_hours:
                explanation["monthly_hours"] = monthly_hours
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


def search_client_file_candidates(
    db: Session,
    q: Optional[str] = None,
    client: Optional[str] = None,
    batch_id: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """
    Search for candidates in the client hours file (messy file) for rematch purposes.
    Returns client-side identities with similarity ranking based on the query.
    """
    latest = repo.latest_batch_id(db, batch_id)
    if not latest:
        return {"candidates": []}
    
    # Get all weekly hours records from the client file
    weekly_rows = db.query(VLookupWeeklyHours).filter(
        VLookupWeeklyHours.upload_batch_id == latest
    ).all()
    
    if not weekly_rows:
        return {"candidates": []}
    
    # Aggregate by candidate name to get unique identities
    from collections import defaultdict
    candidate_map = defaultdict(lambda: {
        "hours": 0,
        "client": "",
        "month": "",
        "weeks": 0,
        "normalized_name": "",
    })
    
    for row in weekly_rows:
        name = row.candidate_name_messy
        candidate_map[name]["hours"] += row.hours_worked or 0
        candidate_map[name]["client"] = row.client_name or candidate_map[name]["client"]
        candidate_map[name]["month"] = row.month or candidate_map[name]["month"]
        candidate_map[name]["weeks"] += 1
        candidate_map[name]["normalized_name"] = row.normalized_name or normalize_name(name)
    
    # Convert to list format
    client_candidates = [
        {
            "candidate_name": name,
            "client_name": data["client"],
            "month": data["month"],
            "total_hours": int(data["hours"]),
            "week_count": data["weeks"],
            "normalized_name": data["normalized_name"],
        }
        for name, data in candidate_map.items()
    ]
    
    query_name = (q or "").strip()
    if not query_name:
        # No query, return first N candidates
        return {
            "candidates": [
                {
                    **c,
                    "why_suggested": f"{c['total_hours']}h across {c['week_count']} weeks",
                    "confidence": 0,
                    "identity_compatible": False,
                }
                for c in sorted(client_candidates, key=lambda x: x["candidate_name"])[:limit]
            ]
        }
    
    # Use the matcher to rank candidates by similarity
    matcher = ReconciliationMatcher()
    
    # Prepare candidates in the format the matcher expects
    template_format = [
        {
            "candidate_name": c["candidate_name"],
            "client_name": c["client_name"],
            "month": c["month"],
        }
        for c in client_candidates
    ]
    
    # Rank using the matcher's similarity algorithm
    ranked = matcher.rank_for_rematch(
        messy_name=query_name,
        template_candidates=template_format,
        messy_client=client,
        limit=limit,
    )
    
    # Enrich with hours data
    name_to_candidate = {c["candidate_name"]: c for c in client_candidates}
    enriched = []
    for r in ranked:
        candidate_name = r.get("candidate_name")
        if candidate_name in name_to_candidate:
            original = name_to_candidate[candidate_name]
            enriched.append({
                "candidate_name": candidate_name,
                "client_name": r.get("client_name"),
                "month": r.get("month"),
                "total_hours": original["total_hours"],
                "week_count": original["week_count"],
                "why_suggested": r.get("why_suggested", "Name similarity match"),
                "confidence": r.get("confidence", 0),
                "identity_compatible": r.get("identity_compatible", False),
            })
    
    # Fallback: simple text search if matcher returns nothing
    if not enriched:
        like = query_name.lower()
        enriched = [
            {
                **c,
                "why_suggested": "Text contains search tokens",
                "confidence": 0,
                "identity_compatible": False,
            }
            for c in client_candidates
            if like in (c["candidate_name"] or "").lower()
        ][:limit]
    
    return {"candidates": enriched}


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
    if match.match_status == "matched" and not match.manually_reviewed:
        raise HTTPException(
            status_code=400,
            detail="Auto-matched candidates do not need Accept or Reject.",
        )

    body = body or VLookupReviewBody()
    match.match_status = "accepted"
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
        "identity_status": "accepted",
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
    if match.match_status == "matched" and not match.manually_reviewed:
        raise HTTPException(
            status_code=400,
            detail="Auto-matched candidates do not need Accept or Reject.",
        )
    if match.match_status == "rejected":
        raise HTTPException(
            status_code=400,
            detail="This candidate is already rejected. Use Restore if it was rejected by mistake.",
        )

    body = body or VLookupReviewBody()
    previous_status = match.match_status
    previous_name = match.template_candidate_name
    explanation = dict(match.match_explanation or {})
    snapshot = {
        "previous_status": previous_status,
        "template_candidate_id": match.template_candidate_id,
        "template_candidate_name": match.template_candidate_name,
        "template_candidate_id_str": match.template_candidate_id_str,
        "confidence_score": match.confidence_score,
        "match_method": match.match_method,
        "identity_summary": explanation.get("identity_summary"),
        "identity_headline": explanation.get("identity_headline"),
    }
    match.match_status = "rejected"
    match.review_action = "rejected"
    repo.touch_reviewed(match, reviewed_by=body.reviewed_by, notes=body.notes)

    rejected_name = f" '{previous_name}'" if previous_name else ""
    summary = (
        f"Rejected: Accounts rejected suggested identity{rejected_name} "
        f"for source '{match.messy_name_original or match.template_candidate_name}'."
    )
    if body.notes:
        summary = f"{summary} Note: {body.notes}"
    explanation["identity_summary"] = summary
    explanation["identity_headline"] = "Rejected"
    explanation["restore_snapshot"] = snapshot
    explanation["audit"] = {
        "what_happened": explanation["identity_headline"],
        "why": summary,
        "identity_status": "rejected",
        "validation_status": (explanation.get("validation") or {}).get("status"),
        "validation_summary": (explanation.get("validation") or {}).get("summary"),
        "has_alternatives": bool(explanation.get("alternatives")),
        "master_candidate": match.template_candidate_name,
        "client_candidate": match.messy_name_original,
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
    match.match_status = "accepted" if body.accept else "needs_review"
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


def rematch_client(
    db: Session, match_id: int, body: "VLookupRematchClientBody"
) -> VLookupActionResponse:
    """
    Rematch a template candidate to a different client file identity.
    This is the correct Smart Match flow: template candidate -> client file candidate.
    """
    from app.models.vlookup.schemas import VLookupRematchClientBody
    
    match = repo.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if not match.template_candidate_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot rematch: no template candidate linked. This match has no master record.",
        )
    
    # Get the template candidate to preserve it
    template = repo.get_template_by_id(db, match.template_candidate_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template candidate not found")
    
    # Find the client file candidate's hours
    batch_id = match.upload_batch_id
    weekly_rows = db.query(VLookupWeeklyHours).filter(
        VLookupWeeklyHours.upload_batch_id == batch_id,
        VLookupWeeklyHours.candidate_name_messy == body.client_candidate_name,
    ).all()
    
    if not weekly_rows:
        raise HTTPException(
            status_code=404,
            detail=f"Client file candidate '{body.client_candidate_name}' not found in this batch",
        )
    
    # Aggregate hours from the client file candidate
    total_hours = sum(row.hours_worked or 0 for row in weekly_rows)
    weekly_breakdown = {}
    monthly_hours = defaultdict(float)
    weekly_by_month = defaultdict(dict)
    client_name = ""
    messy_month = ""
    
    for row in weekly_rows:
        week = row.week or "Week"
        month = row.month or ""
        hours = row.hours_worked or 0
        
        weekly_breakdown[week] = weekly_breakdown.get(week, 0) + hours
        if month:
            monthly_hours[month] += hours
            if week not in weekly_by_month[month]:
                weekly_by_month[month][week] = 0
            weekly_by_month[month][week] += hours
            messy_month = month
        
        if row.client_name and not client_name:
            client_name = row.client_name
    
    # Update the match to point to the new client file identity
    match.messy_name_original = body.client_candidate_name
    match.messy_client_name = client_name
    match.messy_month = messy_month
    match.total_hours = int(total_hours)
    match.weekly_breakdown = weekly_breakdown
    match.monthly_hours = dict(monthly_hours)
    match.weekly_by_month = {k: dict(v) for k, v in weekly_by_month.items()}
    match.match_method = "manual_rematch"
    match.review_action = "rematched_client"
    match.confidence_score = 100.0
    match.match_status = "accepted" if body.accept else "needs_review"
    repo.touch_reviewed(match, reviewed_by=body.reviewed_by, notes=body.notes)
    
    # Update explanation
    explanation = dict(match.match_explanation or {})
    summary = (
        f"Rematched: Template candidate '{template.candidate_name}' ({template.candidate_id}) "
        f"linked to client file identity '{body.client_candidate_name}' ({total_hours}h)."
    )
    if body.notes:
        summary = f"{summary} Note: {body.notes}"
    
    explanation["identity_summary"] = summary
    explanation["identity_headline"] = f"Rematched: {template.candidate_name} → {body.client_candidate_name}"
    explanation["manual_rematch"] = {
        "template_candidate_id": template.candidate_id,
        "template_candidate_name": template.candidate_name,
        "client_candidate_name": body.client_candidate_name,
        "client_name": client_name,
        "total_hours": int(total_hours),
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
    
    # Audit log
    audit_service.record_event(
        db,
        action=AuditAction.HOURS_RECONCILIATION,
        title="Template candidate rematched to client file identity",
        details=(
            f"Template candidate '{template.candidate_name}' ({template.candidate_id}) "
            f"rematched to client file identity '{body.client_candidate_name}' "
            f"with {total_hours}h by {body.reviewed_by}"
        ),
        user=None,
        metadata={
            "match_id": match_id,
            "template_candidate_id": template.candidate_id,
            "template_candidate_name": template.candidate_name,
            "client_candidate_name": body.client_candidate_name,
            "total_hours": int(total_hours),
            "reviewed_by": body.reviewed_by,
            "notes": body.notes,
        },
        entity_type="vlookup_match",
        entity_id=str(match_id),
    )
    
    db.commit()
    
    return VLookupActionResponse(
        match_id=match_id,
        message=f"Template candidate rematched to '{body.client_candidate_name}'",
        template_candidate_id=template.candidate_id,
        template_candidate_name=template.candidate_name,
    )


def restore_match(
    db: Session, match_id: int, body: Optional[VLookupReviewBody] = None
) -> VLookupActionResponse:
    match = repo.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.match_status != "rejected":
        raise HTTPException(
            status_code=400,
            detail="Only rejected candidates can be restored.",
        )

    body = body or VLookupReviewBody()
    explanation = dict(match.match_explanation or {})
    snapshot = explanation.get("restore_snapshot") or {}
    previous_status = snapshot.get("previous_status") or "needs_review"
    if previous_status not in repo.VALID_STATUSES or previous_status == "rejected":
        previous_status = "needs_review"

    match.match_status = previous_status
    match.review_action = "restored"
    if snapshot.get("template_candidate_id"):
        match.template_candidate_id = snapshot.get("template_candidate_id")
    if snapshot.get("template_candidate_name"):
        match.template_candidate_name = snapshot.get("template_candidate_name")
    if snapshot.get("template_candidate_id_str"):
        match.template_candidate_id_str = snapshot.get("template_candidate_id_str")
    if snapshot.get("confidence_score") is not None:
        match.confidence_score = float(snapshot.get("confidence_score") or 0)
    if snapshot.get("match_method"):
        match.match_method = snapshot.get("match_method")
    repo.touch_reviewed(match, reviewed_by=body.reviewed_by, notes=body.notes)

    summary = (
        f"Restored: candidate returned to '{previous_status.replace('_', ' ')}' "
        f"after accidental reject."
    )
    if body.notes:
        summary = f"{summary} Note: {body.notes}"
    explanation["identity_summary"] = snapshot.get("identity_summary") or summary
    explanation["identity_headline"] = snapshot.get("identity_headline") or (
        f"Restored: {match.template_candidate_name or 'candidate'}"
    )
    explanation["audit"] = {
        "what_happened": explanation["identity_headline"],
        "why": summary,
        "identity_status": previous_status,
        "validation_status": (explanation.get("validation") or {}).get("status"),
        "validation_summary": (explanation.get("validation") or {}).get("summary"),
        "has_alternatives": bool(explanation.get("alternatives")),
        "master_candidate": match.template_candidate_name,
        "client_candidate": match.messy_name_original,
    }
    match.match_explanation = explanation
    db.commit()
    return VLookupActionResponse(match_id=match_id, message="Candidate restored")


def list_hours_template(
    db: Session, batch_id: Optional[str] = None
) -> Dict[str, Any]:
    latest = repo.latest_batch_id(db, batch_id)
    rows = repo.list_templates_for_batch(db, latest)
    candidates = [repo.serialize_template_candidate(row) for row in rows]
    return {
        "batch_id": latest,
        "count": len(candidates),
        "candidates": candidates,
    }


def list_messy_file(
    db: Session, batch_id: Optional[str] = None
) -> Dict[str, Any]:
    """Read-only aggregated identities from the uploaded client (messy) hours file."""
    latest = repo.latest_batch_id(db, batch_id)
    rows = repo.list_weekly_hours_for_batch(db, latest)
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        name = str(row.candidate_name_messy or "").strip()
        client = str(row.client_name or "").strip()
        key = (name.lower(), client.lower())
        dest = merged.get(key)
        if dest is None:
            dest = {
                "candidate_name": name,
                "client_name": client or None,
                "normalized_name": row.normalized_name,
                "monthly_hours": {},
                "total_hours": 0,
                "week_count": 0,
            }
            merged[key] = dest
        month = str(row.month or "").strip() or "unknown"
        hours = int(row.hours_worked or 0)
        dest["monthly_hours"][month] = float(dest["monthly_hours"].get(month, 0)) + hours
        dest["total_hours"] = int(dest["total_hours"]) + hours
        dest["week_count"] = int(dest["week_count"]) + 1
        if len(name) > len(str(dest.get("candidate_name") or "")):
            dest["candidate_name"] = name
    identities = sorted(
        merged.values(),
        key=lambda item: (str(item.get("candidate_name") or "").lower(), str(item.get("client_name") or "").lower()),
    )
    return {
        "batch_id": latest,
        "count": len(identities),
        "identities": identities,
    }


def _hours_for_export_month(match: VLookupMatchedRecord, month_key: str) -> float | int:
    """
    Return hours for export, preserving int/float format.
    If hours are a whole number, return int. Otherwise return float.
    """
    explanation = match.match_explanation or {}
    monthly = explanation.get("monthly_hours") or {}
    
    hours_value = None
    if month_key and monthly.get(month_key) is not None:
        try:
            hours_value = float(monthly.get(month_key) or 0)
        except (TypeError, ValueError):
            return 0
    elif month_key and normalize_month_year(str(match.messy_month or "")) == month_key:
        hours_value = float(match.total_hours or 0)
    elif not month_key:
        hours_value = float(match.total_hours or 0)
    else:
        return 0
    
    # Return int if it's a whole number, otherwise float
    if hours_value is not None and hours_value == int(hours_value):
        return int(hours_value)
    return hours_value if hours_value is not None else 0


def _match_belongs_to_month(
    match: VLookupMatchedRecord,
    template: Optional[VLookupTemplateCandidate],
    month_key: Optional[str],
) -> bool:
    if not month_key:
        return True
    messy = normalize_month_year(str(match.messy_month or ""))
    tmpl = normalize_month_year(str(getattr(template, "month", None) or ""))
    return messy == month_key or tmpl == month_key


def _dedupe_export_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep one row per Candidate ID + Client + Month (accepted beats matched)."""
    status_rank = {"accepted": 2, "matched": 1}
    chosen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        candidate_id = str(row.get("Candidate ID") or "").strip().lower()
        name = str(row.get("Candidate Name") or row.get("Source Name") or "").strip().lower()
        client = str(row.get("Client Name") or row.get("Client Name (Source)") or "").strip().lower()
        month = str(row.get("Month") or "").strip()
        key = f"{candidate_id or name}::{client}::{month}"
        prev = chosen.get(key)
        if prev is None:
            chosen[key] = row
            continue
        prev_rank = status_rank.get(str(prev.get("Match Status") or ""), 0)
        next_rank = status_rank.get(str(row.get("Match Status") or ""), 0)
        prev_conf = float(prev.get("Confidence") or 0)
        next_conf = float(row.get("Confidence") or 0)
        if next_rank > prev_rank or (next_rank == prev_rank and next_conf > prev_conf):
            chosen[key] = row
    return list(chosen.values())


def _hours_export_rows(
    db: Session,
    *,
    batch_id: Optional[str] = None,
    statuses: Sequence[str],
    month_key: Optional[str] = None,
    require_template: bool = True,
) -> Tuple[str, List[Dict[str, Any]], str]:
    latest = repo.latest_batch_id(db, batch_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No matches found")

    batch = repo.get_batch(db, latest)
    batch_month = normalize_month_year(str(getattr(batch, "target_month", None) or ""))
    requested_month = normalize_month_year(str(month_key or "")) or batch_month
    available_months = repo.list_months_for_batch(db, latest)
    if not requested_month and available_months:
        requested_month = available_months[-1]

    matches = repo.list_matches_for_download(db, latest, statuses, requested_month)
    data: List[Dict[str, Any]] = []
    for match in matches:
        if match.review_action == "rejected" or match.match_status == "rejected":
            continue
        template = (
            repo.get_template_by_id(db, match.template_candidate_id)
            if match.template_candidate_id
            else None
        )
        if require_template and not match.template_candidate_id:
            continue
        if not _match_belongs_to_month(match, template, requested_month):
            continue
        hours = _hours_for_export_month(match, requested_month)
        month_value = requested_month or (
            normalize_month_year(str(match.messy_month or ""))
            or normalize_month_year(str(template.month if template and template.month else ""))
            or batch_month
            or ""
        )
        explanation = match.match_explanation or {}
        data.append(
            {
                "Candidate ID": match.template_candidate_id_str or "",
                "Candidate Name": match.template_candidate_name
                or match.messy_name_original
                or "",
                "Client Name": (template.client_name if template else "")
                or (match.messy_client_name or ""),
                "Hours Worked": hours,
                "Month": month_value,
                "Match Status": match.match_status,
                "Confidence": match.confidence_score,
                "Client Name (Source)": match.messy_client_name or "",
                "Source Name": match.messy_name_original or "",
                "Cumulative Hours (Client File)": explanation.get("cumulative_hours"),
                "Hours Note": explanation.get("hours_note") or "",
            }
        )
    return latest, _dedupe_export_rows(data), requested_month or ""


def _matched_hours_export_rows(
    db: Session,
    batch_id: Optional[str] = None,
    include_review_pending: bool = False,
    month_key: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build filled Hours Template rows for the selected month.

    Only review-complete matches: auto-matched + manually accepted.
    Unmatched stay in the database for audit and are not included here.
    """
    statuses = ["matched", "accepted"]
    if include_review_pending:
        statuses.extend(["needs_review", "potential_duplicate", "conflicting"])
    latest, data, _month = _hours_export_rows(
        db,
        batch_id=batch_id,
        statuses=statuses,
        month_key=month_key,
        require_template=True,
    )
    return latest, data


def _excel_download(
    data: List[Dict[str, Any]],
    filename: str,
    *,
    extra_cols: Optional[List[str]] = None,
) -> StreamingResponse:
    df = pd.DataFrame(data)
    export_cols = [
        "Candidate ID",
        "Candidate Name",
        "Client Name",
        "Hours Worked",
        "Month",
    ]
    audit_cols = export_cols + (extra_cols or [
        "Match Status",
        "Confidence",
        "Client Name (Source)",
        "Source Name",
        "Cumulative Hours (Client File)",
        "Hours Note",
    ])
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        (df[export_cols] if not df.empty else pd.DataFrame(columns=export_cols)).to_excel(
            writer, sheet_name="Hours Template", index=False
        )
        (df[audit_cols] if not df.empty else pd.DataFrame(columns=audit_cols)).to_excel(
            writer, sheet_name="Audit Detail", index=False
        )
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def download_matches(
    db: Session,
    batch_id: Optional[str] = None,
    include_review_pending: bool = False,
    month_key: Optional[str] = None,
    user: Optional[User] = None,
) -> StreamingResponse:
    latest, data = _matched_hours_export_rows(
        db,
        batch_id=batch_id,
        include_review_pending=include_review_pending,
        month_key=month_key,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    month_part = f"_{normalize_month_year(str(month_key or ''))}" if month_key else ""
    filename = f"hours_reconciled{month_part}_{stamp}.xlsx"
    audit_service.record_event(
        db,
        action=AuditAction.FILE_DOWNLOAD,
        title="Downloaded reconciled hours",
        details=f"Downloaded {filename} with {len(data)} row(s) for batch {latest}",
        user=user,
        metadata={"batch_id": latest, "filename": filename, "row_count": len(data), "month": month_key},
        entity_type="vlookup_batch",
        entity_id=str(latest) if latest else None,
    )
    _mark_batch_completed(db, latest, user=user)
    return _excel_download(data, filename)


def download_unmatched(
    db: Session,
    batch_id: Optional[str] = None,
    month_key: Optional[str] = None,
    user: Optional[User] = None,
) -> StreamingResponse:
    latest, data, requested_month = _hours_export_rows(
        db,
        batch_id=batch_id,
        statuses=["unmatched"],
        month_key=month_key,
        require_template=False,
    )
    _ = latest
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    month_part = f"_{requested_month}" if requested_month else ""
    filename = f"hours_unmatched{month_part}_{stamp}.xlsx"
    audit_service.record_event(
        db,
        action=AuditAction.FILE_DOWNLOAD,
        title="Downloaded unmatched hours",
        details=f"Downloaded {filename} with {len(data)} unmatched row(s)",
        user=user,
        metadata={"batch_id": latest, "filename": filename, "row_count": len(data), "month": requested_month},
        entity_type="vlookup_batch",
        entity_id=str(latest) if latest else None,
    )
    db.commit()
    return _excel_download(data, filename)


def publish_hours_from_batch(
    db: Session,
    *,
    batch_id: Optional[str] = None,
    division: Optional[str] = None,
    include_review_pending: bool = False,
    month_key: Optional[str] = None,
    uploaded_by: Optional[int] = None,
) -> VLookupPublishHoursResponse:
    """
    Persist matched VLOOKUP rows into Hours & Benchmark tables
    (`hours_data_versions` / `hours_rows`). This is the DB source of truth for Hours Worked.
    """
    latest, data = _matched_hours_export_rows(
        db,
        batch_id=batch_id,
        include_review_pending=include_review_pending,
        month_key=month_key,
    )
    if not data:
        raise HTTPException(
            status_code=400,
            detail="No matched hours rows to publish. Accept matches first.",
        )

    rows_by_key: Dict[str, HoursRowIn] = {}
    month_keys: List[str] = []
    skipped_no_month: List[str] = []
    for item in data:
        external_id = str(item.get("Candidate ID") or "").strip()
        if not external_id:
            continue
        month_raw = str(item.get("Month") or "").strip()
        month_key = normalize_month_year(month_raw)
        if not month_key:
            skipped_no_month.append(external_id)
            continue
        month_keys.append(month_key)
        hours_raw = item.get("Hours Worked")
        try:
            hours_worked = Decimal(str(hours_raw if hours_raw is not None else 0))
        except Exception:
            hours_worked = Decimal("0")
        client = str(item.get("Client Name") or "").strip() or None
        # Latest matched row wins for Candidate ID + Client + Month
        dedupe_key = f"{external_id.lower()}::{(client or '').lower()}::{month_key}"
        rows_by_key[dedupe_key] = HoursRowIn(
            external_candidate_id=external_id,
            hours_worked=hours_worked,
            month_key=month_key,
            client=client,
            raw_candidate_name=str(item.get("Candidate Name") or "") or None,
        )

    rows = list(rows_by_key.values())
    if not rows:
        detail_parts = ["No valid Candidate ID + Month rows to publish."]
        if skipped_no_month:
            detail_parts.append(
                "Missing/invalid month for Candidate ID(s): "
                + ", ".join(sorted(set(skipped_no_month))[:20])
            )
        raise HTTPException(status_code=400, detail=" ".join(detail_parts))

    known_rows: List[HoursRowIn] = []
    for row in rows:
        external = str(row.external_candidate_id or "").strip()
        if not external:
            continue
        if candidate_repository.get_candidate_by_external_id(db, external) is None:
            continue
        known_rows.append(row)

    primary_month = Counter(month_keys).most_common(1)[0][0]
    if not known_rows:
        # Hours Template IDs often are not in Candidate Master. Download still works;
        # Hours & Benchmark publish is skipped instead of failing the request.
        return VLookupPublishHoursResponse(
            status="skipped",
            batch_id=latest,
            hours_version_id=0,
            row_count=0,
            division=division,
            month_key=primary_month,
            version_label="",
        )

    version_label = f"VLOOKUP {primary_month} ({latest[:8]})"
    payload = CreateHoursVersionRequest(
        version_label=version_label,
        division=division,
        source_filename=f"vlookup_batch_{latest}.xlsx",
        notes=f"Published from VLOOKUP batch {latest}",
        rows=known_rows,
    )
    detail = hours_service.create_version(db, payload, uploaded_by=uploaded_by)
    return VLookupPublishHoursResponse(
        status="success",
        batch_id=latest,
        hours_version_id=detail.version.id,
        row_count=len(detail.rows),
        division=division,
        month_key=primary_month,
        version_label=detail.version.version_label,
    )


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
    template_months: list,
    available_months: list,
    template_month: str = "",
) -> Optional[str]:
    if explicit:
        return normalize_month_year(explicit)

    normalized_available = [normalize_month_year(m) for m in available_months if m]
    normalized_template = [
        normalize_month_year(m) for m in (template_months or []) if m
    ]
    if template_month:
        tm = normalize_month_year(template_month)
        if tm and tm not in normalized_template:
            normalized_template.append(tm)

    overlap = [m for m in normalized_template if m in normalized_available]
    if overlap:
        return sorted(set(overlap))[-1]
    # Do not fall back to an unrelated client-file month/year.
    if normalized_template:
        return sorted(set(normalized_template))[0]
    if normalized_available:
        return sorted(normalized_available)[-1]
    return None


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


def _actor(user: Optional[User]) -> str:
    if user is None:
        return "system"
    return getattr(user, "email", None) or str(user.id)


def _write_vlookup_audit(
    db: Session,
    *,
    action: AuditAction,
    title: str,
    details: str,
    user: Optional[User],
    batch: VLookupUploadBatch,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    metadata = {
        "batch_id": batch.batch_id,
        "filename": batch.filename,
        "target_month": batch.target_month,
        "cycle_id": batch.cycle_id,
        "status": batch.status,
        "stage": batch.stage,
        **(extra or {}),
    }
    audit_repository.write_log(
        db,
        action=action,
        title=title,
        details=details,
        user_display=(user.full_name if user and user.full_name else _actor(user)),
        username=_actor(user),
        metadata=metadata,
        entity_type="vlookup_batch",
        entity_id=batch.batch_id,
        user_id=getattr(user, "id", None),
    )


def _draft_out(batch: VLookupUploadBatch) -> VLookupDraftOut:
    return VLookupDraftOut(**repo.serialize_batch(batch))


def _require_batch(db: Session, batch_id: str) -> VLookupUploadBatch:
    batch = repo.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="VLOOKUP batch not found")
    return batch


def _mark_batch_completed(
    db: Session,
    batch_id: Optional[str],
    user: Optional[User] = None,
) -> None:
    if not batch_id:
        return
    batch = repo.get_batch(db, batch_id)
    if not batch or batch.status == "completed":
        return
    previous = batch.status
    batch.status = "completed"
    batch.stage = "completed"
    batch.completed_at = datetime.utcnow()
    _write_vlookup_audit(
        db,
        action=AuditAction.VLOOKUP_MATCH_COMPLETED,
        title="VLOOKUP match completed",
        details=(
            f"VLOOKUP batch {batch.batch_id} completed "
            f"(file: {batch.filename or 'n/a'}, previous status: {previous})."
        ),
        user=user,
        batch=batch,
        extra={"previous_status": previous, "new_status": "completed"},
    )
    db.commit()


def cancel_batch(
    db: Session,
    batch_id: str,
    user: User,
    body: Optional[VLookupCancelBody] = None,
) -> VLookupDraftOut:
    batch = _require_batch(db, batch_id)
    if batch.status == "draft":
        return _draft_out(batch)
    if batch.status == "failed":
        raise HTTPException(status_code=409, detail="Failed VLOOKUP batches cannot be saved as drafts")
    previous = batch.status
    payload = body or VLookupCancelBody()
    now = datetime.utcnow()
    resume_state = dict(batch.resume_state or {})
    resume_state.update(
        {
            "stage": batch.stage or "review",
            "target_month": payload.month or batch.target_month,
            "tab": payload.tab,
            "filename": batch.filename,
            "file_type": batch.file_type,
            "matched_count": batch.matched_count,
            "needs_review_count": batch.needs_review_count,
            "unmatched_count": batch.unmatched_count,
            "notes": payload.notes,
        }
    )
    batch.status = "draft"
    batch.stage = batch.stage or "review"
    batch.cancelled_at = now
    batch.cancelled_by = _actor(user)
    batch.resume_state = resume_state
    if payload.month:
        batch.target_month = payload.month
    _write_vlookup_audit(
        db,
        action=AuditAction.VLOOKUP_MATCH_CANCELLED,
        title="VLOOKUP match cancelled",
        details=(
            f"VLOOKUP matching for {batch.filename or batch.batch_id} was cancelled and saved as a draft."
        ),
        user=user,
        batch=batch,
        extra={"previous_status": previous, "new_status": "draft"},
    )
    db.commit()
    db.refresh(batch)
    return _draft_out(batch)


def list_drafts(db: Session) -> VLookupDraftListResponse:
    rows = repo.list_draft_batches(db)
    return VLookupDraftListResponse(drafts=[_draft_out(row) for row in rows])


def get_draft(db: Session, batch_id: str) -> VLookupDraftOut:
    batch = _require_batch(db, batch_id)
    if batch.status != "draft":
        raise HTTPException(status_code=404, detail="VLOOKUP draft not found")
    return _draft_out(batch)


def continue_draft(db: Session, batch_id: str, user: User) -> VLookupDraftOut:
    batch = _require_batch(db, batch_id)
    if batch.status in {"running", "completed"}:
        return _draft_out(batch)
    if batch.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot continue a VLOOKUP batch with status {batch.status}",
        )
    previous = batch.status
    batch.status = "running"
    batch.stage = batch.stage or "review"
    _write_vlookup_audit(
        db,
        action=AuditAction.VLOOKUP_DRAFT_RESUMED,
        title="VLOOKUP draft resumed",
        details=f"VLOOKUP draft {batch.filename or batch.batch_id} was resumed.",
        user=user,
        batch=batch,
        extra={"previous_status": previous, "new_status": "running"},
    )
    db.commit()
    db.refresh(batch)
    return _draft_out(batch)


def discard_draft(db: Session, batch_id: str, user: User) -> Dict[str, str]:
    batch = _require_batch(db, batch_id)
    if batch.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft VLOOKUP batches can be discarded")
    repo.delete_batch_data(db, batch_id)
    audit_repository.write_log(
        db,
        action=AuditAction.SYSTEM,
        title="VLOOKUP draft discarded",
        details=f"VLOOKUP draft {batch.filename or batch_id} was discarded.",
        user_display=(user.full_name if user.full_name else _actor(user)),
        username=_actor(user),
        metadata={"batch_id": batch_id, "filename": batch.filename},
        entity_type="vlookup_batch",
        entity_id=batch_id,
        user_id=user.id,
    )
    db.commit()
    return {"status": "deleted", "batch_id": batch_id}



def edit_candidate_hours(
    db: Session,
    match_id: int,
    body: "ManualEditHoursBody",
    user: User,
) -> VLookupActionResponse:
    """
    Edit candidate hours manually for benchmark purposes.
    Useful when hours were mistakenly not met and need adjustment.
    
    For unmatched candidates, automatically accepts the match after editing hours,
    allowing the candidate to be exported for incentive processing.
    """
    from app.models.vlookup.schemas import ManualEditHoursBody
    
    match = repo.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    was_unmatched = match.match_status == "unmatched"
    
    # Store old hours before updating
    old_hours = match.total_hours
    
    # Update hours - store as int if whole number, float otherwise
    if body.total_hours == int(body.total_hours):
        match.total_hours = int(body.total_hours)
        total_hours_for_json = int(body.total_hours)
    else:
        match.total_hours = int(round(body.total_hours))  # DB column is int
        total_hours_for_json = body.total_hours  # Preserve float in JSON
    
    # Start building explanation updates
    explanation = dict(match.match_explanation or {})
    
    # Update weekly breakdown if provided
    if body.weekly_breakdown:
        match.weekly_breakdown = {
            str(k): float(v) for k, v in body.weekly_breakdown.items()
        }
        # Recalculate month-by-month hours and weekly_by_month
        month_hours = {}
        weekly_by_month = {}
        for week, hours in body.weekly_breakdown.items():
            # Assign to the specified month
            week_hours = float(hours) if hours != int(hours) else int(hours)
            month_hours[body.month] = month_hours.get(body.month, 0) + hours
            if body.month not in weekly_by_month:
                weekly_by_month[body.month] = {}
            weekly_by_month[body.month][week] = week_hours
        
        # Convert month total to int if it's a whole number
        if month_hours[body.month] == int(month_hours[body.month]):
            month_hours[body.month] = int(month_hours[body.month])
        
        # Store in match_explanation for frontend
        explanation["weekly_by_month"] = weekly_by_month
        explanation["monthly_hours"] = month_hours
    else:
        # Clear weekly breakdown, use total only
        match.weekly_breakdown = {}
        # Store in match_explanation
        explanation["weekly_by_month"] = {}
        explanation["monthly_hours"] = {body.month: total_hours_for_json}
    
    # Update month if changed
    if body.month:
        match.messy_month = normalize_month_year(body.month) or body.month
    
    # Update review tracking
    match.manually_reviewed = True
    match.review_action = "manual_edit"
    repo.touch_reviewed(match, reviewed_by=body.reviewed_by, notes=body.notes)
    
    # Add manual edit info to explanation
    edit_note = (
        f"Hours manually edited by {body.reviewed_by} for benchmark purposes. "
        f"Total: {body.total_hours}h for {body.month}."
    )
    if body.notes:
        edit_note = f"{edit_note} Note: {body.notes}"
    
    explanation["manual_edit"] = {
        "edited_by": body.reviewed_by,
        "timestamp": datetime.utcnow().isoformat(),
        "total_hours": body.total_hours,
        "month": body.month,
        "notes": body.notes,
        "reason": "benchmark_adjustment",
    }
    
    # Auto-accept unmatched candidates after editing hours
    if was_unmatched:
        match.match_status = "accepted"
        match.review_action = "accepted"
        edit_note = (
            f"{edit_note} Automatically accepted after manual hours edit - "
            f"candidate can now be exported for incentive processing."
        )
        explanation["auto_accepted_after_edit"] = {
            "accepted_at": datetime.utcnow().isoformat(),
            "accepted_by": body.reviewed_by,
            "reason": "unmatched_candidate_hours_manually_added",
        }
        explanation["identity_headline"] = f"Accepted: {match.template_candidate_name}"
    
    explanation["identity_summary"] = edit_note
    
    # Apply all explanation updates at once
    match.match_explanation = explanation
    
    # Audit log
    audit_title = "Candidate hours manually edited"
    audit_details = (
        f"Hours for {match.template_candidate_name or match.messy_name_original} "
        f"edited to {body.total_hours}h for {body.month} by {body.reviewed_by}"
    )
    
    if was_unmatched:
        audit_title = "Unmatched candidate hours edited and accepted"
        audit_details = f"{audit_details}. Automatically accepted for export."
    
    audit_service.record_event(
        db,
        action=AuditAction.HOURS_RECONCILIATION,
        title=audit_title,
        details=audit_details,
        user=user,
        metadata={
            "match_id": match_id,
            "candidate_name": match.template_candidate_name or match.messy_name_original,
            "old_hours": old_hours,
            "new_hours": body.total_hours,
            "month": body.month,
            "reviewed_by": body.reviewed_by,
            "notes": body.notes,
            "was_unmatched": was_unmatched,
            "auto_accepted": was_unmatched,
        },
        entity_type="vlookup_match",
        entity_id=str(match_id),
    )
    
    db.commit()
    
    message = f"Hours updated to {body.total_hours}h for {body.month}"
    if was_unmatched:
        message = f"{message} and automatically accepted for export"
    
    return VLookupActionResponse(
        match_id=match_id,
        message=message,
        template_candidate_id=match.template_candidate_id_str,
        template_candidate_name=match.template_candidate_name,
    )


def manual_add_candidate(
    db: Session,
    body: "ManualAddCandidateBody",
    user: User,
) -> VLookupActionResponse:
    """
    Manually add a candidate with hours for benchmark purposes.
    Creates a new matched record in the specified batch.
    """
    from app.models.vlookup.schemas import ManualAddCandidateBody
    
    batch_id = body.batch_id
    batch = repo.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="VLOOKUP batch not found")
    
    # Normalize month
    month_key = normalize_month_year(body.month) or body.month
    
    # Check if candidate already exists in template for this batch
    template_candidate = None
    if body.candidate_id:
        existing_templates = repo.list_templates_for_batch(db, batch_id)
        for t in existing_templates:
            if t.candidate_id == body.candidate_id:
                template_candidate = t
                break
    
    # If not found, create a new template entry
    if not template_candidate:
        template_candidate = VLookupTemplateCandidate(
            candidate_id=body.candidate_id or f"MANUAL-{uuid.uuid4().hex[:8].upper()}",
            candidate_name=body.candidate_name,
            client_name=body.client_name or "",
            template_hours=int(round(body.total_hours)),
            month=month_key,
            contract_type="",
            division="",
            recruiter_name="",
            upload_batch_id=batch_id,
        )
        db.add(template_candidate)
        db.flush()
    
    # Calculate weekly breakdown by month
    weekly_by_month = {}
    if body.weekly_breakdown:
        weekly_by_month[month_key] = {
            str(k): float(v) for k, v in body.weekly_breakdown.items()
        }
    
    # Create matched record
    matched_record = VLookupMatchedRecord(
        template_candidate_id=template_candidate.id,
        template_candidate_name=body.candidate_name,
        template_candidate_id_str=template_candidate.candidate_id,
        messy_name_original=body.candidate_name,
        messy_client_name=body.client_name or "",
        messy_month=month_key,
        weekly_breakdown=body.weekly_breakdown if body.weekly_breakdown else {},
        weekly_by_month=weekly_by_month,
        total_hours=int(round(body.total_hours)),
        monthly_hours={month_key: body.total_hours},
        confidence_score=100.0,
        match_status="accepted",
        match_method="manual",
        match_explanation={
            "identity_summary": (
                f"Manually added by {body.reviewed_by} for benchmark purposes. "
                f"Total: {body.total_hours}h for {month_key}."
                + (f" Note: {body.notes}" if body.notes else "")
            ),
            "identity_headline": f"Manual: {body.candidate_name}",
            "manual_add": {
                "added_by": body.reviewed_by,
                "timestamp": datetime.utcnow().isoformat(),
                "total_hours": body.total_hours,
                "month": month_key,
                "notes": body.notes,
                "reason": "benchmark_adjustment",
            },
        },
        upload_batch_id=batch_id,
        manually_reviewed=True,
        review_action="manual_add",
        reviewed_by=body.reviewed_by,
        reviewed_at=datetime.utcnow(),
        review_notes=body.notes,
    )
    db.add(matched_record)
    
    # Update batch counts
    batch.matched_count = (batch.matched_count or 0) + 1
    batch.total_records = (batch.total_records or 0) + 1
    
    # Audit log
    audit_service.record_event(
        db,
        action=AuditAction.HOURS_RECONCILIATION,
        title="Candidate manually added",
        details=(
            f"Candidate {body.candidate_name} manually added "
            f"with {body.total_hours}h for {month_key} by {body.reviewed_by}"
        ),
        user=user,
        metadata={
            "batch_id": batch_id,
            "candidate_id": template_candidate.candidate_id,
            "candidate_name": body.candidate_name,
            "client_name": body.client_name,
            "total_hours": body.total_hours,
            "month": month_key,
            "reviewed_by": body.reviewed_by,
            "notes": body.notes,
        },
        entity_type="vlookup_batch",
        entity_id=batch_id,
    )
    
    db.commit()
    db.refresh(matched_record)
    
    return VLookupActionResponse(
        match_id=matched_record.id,
        message=f"Candidate {body.candidate_name} added with {body.total_hours}h for {month_key}",
        template_candidate_id=template_candidate.candidate_id,
        template_candidate_name=body.candidate_name,
    )
