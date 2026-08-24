"""Cycle service — orchestration."""

import calendar
import io
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.models.cycles.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    ApproveRequest,
    CalculateResult,
    ChecklistOut,
    ChecklistUpdate,
    CycleApprovalResultOut,
    CycleCreate,
    CycleOut,
    CycleSummary,
    CycleUpdate,
    HoursUploadOut,
    MatchOut,
    MatchStatsOut,
    MatchUpdate,
    PaymentStatusOut,
    PaymentStatusUpdate,
    ValidationOut,
)
from app.models.incentives.schemas import IncentiveLineOut
from app.repositories.candidates import candidate_repository
from app.repositories.cycles import cycle_repository
from app.repositories.entities.cycle import CycleStatus, MatchResult
from app.repositories.entities.candidate import Candidate
from app.repositories.entities.audit import AuditAction
from app.repositories.entities.user import User
from app.repositories.hours import hours_repository
from app.repositories.incentives import incentive_repository
from app.services.audit import audit_service
from app.services.cycles.cycle_candidates import (
    candidate_matches_division,
    is_seed_candidate,
    resolve_candidates_for_cycle,
)
from app.services.cycles.cycle_engine import run_cycle_calculation
from app.services.cycles.engines.ampcus_client import coordinator_index, is_ampcus_client_division
from app.services.cycles.engines.ampcus_inhouse import is_ampcus_inhouse_division
from app.services.cycles.engines.sambhaji_nagar import is_sambhaji_nagar_division
from app.services.cycles.division_resolver import resolve_candidate_division
from app.services.cycles.hours_name_matcher import HoursMatchRow
from app.services.cycles.hours_name_matcher import (
    ID_FALLBACK,
    NAME_AND_ID,
    NAME_ID_MISMATCH,
    UNMATCHED,
    HoursMatchRow,
    MasterCandidate,
    build_id_index,
    build_name_index,
    match_hours_row,
)
from app.services.cycles.hours_template_parser import parse_hours_template
from app.services.incentives.nashik_calculator import CycleWindow


def create_cycle(db: Session, payload: CycleCreate, created_by: Optional[int] = None) -> CycleOut:
    data = payload.model_dump()
    data["created_by"] = created_by
    data["status"] = CycleStatus.DRAFT
    cycle = cycle_repository.create_cycle(db, data)
    cycle_repository.ensure_default_checklist(db, cycle.id)
    if is_ampcus_client_division(cycle.division) or is_sambhaji_nagar_division(cycle.division):
        candidates = candidate_repository.list_all_candidates(db)
        ids: list[int] = []
        for cand in candidates:
            resolved = resolve_candidate_division(
                organization=cand.organization,
                recruiter_work_location=cand.recruiter_location,
                contract_type=cand.contract_type,
                master_division=cand.division,
            )
            if cycle.division and resolved.resolved_division == cycle.division:
                ids.append(cand.id)
        cycle_repository.ensure_payment_statuses(db, cycle.id, ids)
    db.commit()
    db.refresh(cycle)
    return CycleOut.model_validate(cycle)


def list_cycles(
    db: Session,
    *,
    division: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> List[CycleOut]:
    rows = cycle_repository.list_cycles(db, division=division, status=status_filter)
    return [CycleOut.model_validate(r) for r in rows]


def get_cycle(db: Session, cycle_id: int) -> CycleOut:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    return CycleOut.model_validate(cycle)


def update_cycle(db: Session, cycle_id: int, payload: CycleUpdate) -> CycleOut:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    updated = cycle_repository.update_cycle(db, cycle, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(updated)
    return CycleOut.model_validate(updated)


def delete_cycle(db: Session, cycle_id: int, user: Optional[User] = None) -> dict:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    status_val = cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status)
    protected = {
        CycleStatus.APPROVED.value,
        CycleStatus.PAID.value,
        CycleStatus.CLOSED.value,
    }
    if status_val.upper() in protected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approved cycles cannot be deleted",
        )
    cycle_label = cycle.incentive_month or str(cycle.id)
    cycle_division = cycle.division
    audit_service.record_event(
        db,
        action=AuditAction.CYCLE_CANCEL,
        title=f"Cancelled cycle {cycle_label}",
        details=f"Cancelled incentive cycle #{cycle_id} ({cycle_label}, {cycle_division}) in {status_val} status",
        user=user,
        metadata={
            "cycle_id": cycle_id,
            "cycle": cycle_label,
            "division": cycle_division,
            "previous_status": status_val,
        },
        entity_type="cycle",
        entity_id=str(cycle_id),
    )
    cycle_repository.delete_cycle(db, cycle)
    db.commit()
    return {"message": "deleted", "id": cycle_id}


def get_summary(db: Session, cycle_id: int) -> CycleSummary:
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    counts = cycle_repository.summary_counts(db, cycle_id)
    status_val = cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status)
    return CycleSummary(cycle_id=cycle_id, status=status_val, **counts)


def list_lines(db: Session, cycle_id: int) -> List[IncentiveLineOut]:
    _require_cycle(db, cycle_id)
    rows = cycle_repository.list_lines(db, cycle_id)
    
    # Pre-fetch candidate information to dynamically populate fields
    candidates = {}
    candidate_ids = {r.candidate_id for r in rows if r.candidate_id is not None}
    if candidate_ids:
        for c in db.query(candidate_repository.Candidate).filter(candidate_repository.Candidate.id.in_(candidate_ids)).all():
            candidates[c.id] = c
            
    out_lines = []
    for r in rows:
        line_out = IncentiveLineOut.model_validate(r)
        cand = candidates.get(r.candidate_id) if r.candidate_id else None
        if cand:
            meta = _parse_explanation(r.explanation_json)
            needs_update = not meta or any(
                k not in meta for k in [
                    "start_date", "contract_type", "candidate_source", 
                    "candidate_id", "external_candidate_id",
                    "recruiter", "team_lead", "manager", "crm", "center_head", "avp"
                ]
            )
            if needs_update:
                new_meta = {
                    "start_date": cand.start_date.isoformat() if cand.start_date else None,
                    "contract_type": cand.contract_type,
                    "candidate_source": cand.candidate_source or cand.organization,
                    "candidate_id": cand.start_id or cand.external_candidate_id or str(cand.id),
                    "external_candidate_id": cand.external_candidate_id,
                    "recruiter": cand.recruiter,
                    "team_lead": cand.team_lead,
                    "manager": cand.manager,
                    "crm": cand.crm,
                    "center_head": cand.center_head,
                    "avp": cand.avp,
                }
                if isinstance(meta, dict):
                    new_meta.update({k: v for k, v in meta.items() if k not in new_meta})
                line_out.explanation_json = json.dumps([new_meta], default=str)
                
        out_lines.append(line_out)
        
    return out_lines


def list_matches(db: Session, cycle_id: int) -> List[MatchOut]:
    _require_cycle(db, cycle_id)
    return [MatchOut.model_validate(r) for r in cycle_repository.list_matches(db, cycle_id)]


def update_match(db: Session, cycle_id: int, match_id: int, payload: MatchUpdate) -> MatchOut:
    _require_cycle(db, cycle_id)
    match = cycle_repository.get_match(db, match_id)
    if match is None or match.cycle_id != cycle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    updated = cycle_repository.update_match(db, match, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(updated)
    return MatchOut.model_validate(updated)


def list_validations(db: Session, cycle_id: int) -> List[ValidationOut]:
    _require_cycle(db, cycle_id)
    return [ValidationOut.model_validate(r) for r in cycle_repository.list_validations(db, cycle_id)]


def list_checklist(db: Session, cycle_id: int) -> List[ChecklistOut]:
    _require_cycle(db, cycle_id)
    items = cycle_repository.ensure_default_checklist(db, cycle_id)
    db.commit()
    return [ChecklistOut.model_validate(r) for r in items]


def update_checklist(
    db: Session,
    cycle_id: int,
    item_id: int,
    payload: ChecklistUpdate,
    user_id: Optional[int] = None,
) -> ChecklistOut:
    _require_cycle(db, cycle_id)
    item = cycle_repository.get_checklist_item(db, item_id)
    if item is None or item.cycle_id != cycle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    updated = cycle_repository.update_checklist_item(
        db,
        item,
        is_checked=payload.is_checked,
        notes=payload.notes,
        checked_by=user_id,
    )
    db.commit()
    db.refresh(updated)
    return ChecklistOut.model_validate(updated)


def list_payment_statuses(db: Session, cycle_id: int) -> List[PaymentStatusOut]:
    cycle = _require_cycle(db, cycle_id)
    rows = cycle_repository.list_payment_statuses(db, cycle_id)
    out: List[PaymentStatusOut] = []
    for row in rows:
        cand = candidate_repository.get_candidate(db, row.candidate_id)
        payload = PaymentStatusOut.model_validate(row).model_dump()
        if cand is not None:
            payload.update(
                {
                    "candidate_name": cand.candidate_name,
                    "external_candidate_id": cand.external_candidate_id,
                    "start_id": cand.start_id,
                    "contract_type": cand.contract_type,
                    "markup_percent": cand.markup_percent,
                    "approved_markup_percentage": cand.approved_markup_percentage,
                }
            )
        out.append(PaymentStatusOut(**payload))
    return out


def update_payment_status(
    db: Session,
    cycle_id: int,
    status_id: int,
    payload: PaymentStatusUpdate,
    user_id: Optional[int] = None,
    user: Optional[User] = None,
) -> PaymentStatusOut:
    cycle = _require_cycle(db, cycle_id)
    row = cycle_repository.get_payment_status(db, status_id)
    if row is None or row.cycle_id != cycle_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment status not found")
    previous_status = row.status
    actor_id = user.id if user is not None else user_id
    updated = cycle_repository.update_payment_status(
        db,
        row,
        status=payload.status,
        payment_received_date=payload.payment_received_date,
        payment_reference=payload.payment_reference,
        notes=payload.notes,
        updated_by=actor_id,
    )
    candidate = candidate_repository.get_candidate(db, updated.candidate_id)
    candidate_name = candidate.candidate_name if candidate else f"Candidate {updated.candidate_id}"
    cycle_label = cycle.incentive_month or str(cycle.id)
    audit_service.record_event(
        db,
        action=AuditAction.PAYMENT_UPDATE,
        title=f"Updated payment status for {candidate_name}",
        details=f"Changed payment status from {previous_status} to {updated.status} for {candidate_name} in cycle {cycle_label}",
        user=user,
        metadata={
            "cycle_id": cycle.id,
            "cycle": cycle_label,
            "candidate_id": updated.candidate_id,
            "previous_status": previous_status,
            "status": updated.status,
        },
        entity_type="cycle",
        entity_id=str(cycle.id),
    )
    db.commit()
    db.refresh(updated)
    return PaymentStatusOut.model_validate(updated)


def list_adjustments(db: Session, cycle_id: int) -> List[AdjustmentOut]:
    _require_cycle(db, cycle_id)
    return [AdjustmentOut.model_validate(r) for r in cycle_repository.list_adjustments(db, cycle_id)]


def create_adjustment(
    db: Session,
    cycle_id: int,
    payload: AdjustmentCreate,
    created_by: Optional[int] = None,
) -> AdjustmentOut:
    _require_cycle(db, cycle_id)
    data = payload.model_dump()
    data["cycle_id"] = cycle_id
    data["created_by"] = created_by
    row = cycle_repository.create_adjustment(db, data)
    db.commit()
    db.refresh(row)
    return AdjustmentOut.model_validate(row)


def approve_cycle(
    db: Session,
    cycle_id: int,
    payload: ApproveRequest,
    user_id: Optional[int] = None,
    user: Optional[User] = None,
) -> CycleOut:
    cycle = _require_cycle(db, cycle_id)
    if is_ampcus_client_division(cycle.division):
        if cycle.status != CycleStatus.CALCULATED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ampcus Client cycle must be calculated before finalization")
    actor_id = user.id if user is not None else user_id
    cycle.status = CycleStatus.APPROVED
    cycle.approved_at = datetime.now(timezone.utc)
    db.add(cycle)
    db.flush()
    snapshot_approval_results(
        db,
        cycle,
        approved_by=actor_id,
        comments=payload.comments if payload else None,
    )
    cycle_label = cycle.incentive_month or str(cycle.id)
    audit_service.record_event(
        db,
        action=AuditAction.CYCLE_APPROVE,
        title=f"Approved cycle {cycle_label}",
        details=f"Finalized incentive cycle {cycle_label} ({cycle.division})",
        user=user,
        metadata={"cycle_id": cycle.id, "cycle": cycle_label, "division": cycle.division, "comments": payload.comments if payload else None},
        entity_type="cycle",
        entity_id=str(cycle.id),
    )
    db.commit()
    db.refresh(cycle)
    return CycleOut.model_validate(cycle)


def list_approval_results(db: Session, cycle_id: int) -> List[CycleApprovalResultOut]:
    _require_cycle(db, cycle_id)
    return [
        CycleApprovalResultOut.model_validate(row)
        for row in cycle_repository.list_approval_results(db, cycle_id)
    ]


def _team_label_from_candidate(cand: Optional[Candidate]) -> str:
    if cand is None:
        return ""
    crm = (cand.crm or "").strip()
    center_head = (cand.center_head or "").strip()
    associate_director = (cand.associate_director or "").strip()
    manager = (cand.manager or "").strip()
    senior_manager = (cand.senior_manager or "").strip()
    team_lead = (cand.team_lead or "").strip()
    if crm:
        return crm
    if center_head:
        return center_head
    if associate_director:
        return associate_director
    parts = [p for p in (crm, center_head, associate_director, manager, senior_manager, team_lead) if p]
    if len(parts) >= 2:
        return f"{parts[0]} and {parts[1]}"
    return parts[0] if parts else ""


def snapshot_approval_results(
    db: Session,
    cycle,
    *,
    approved_by: Optional[int] = None,
    comments: Optional[str] = None,
) -> list:
    lines = cycle_repository.list_lines(db, cycle.id)
    candidate_ids = [line.candidate_id for line in lines if line.candidate_id]
    candidates: dict[int, Candidate] = {}
    if candidate_ids:
        for cand in db.query(Candidate).filter(Candidate.id.in_(candidate_ids)).all():
            candidates[cand.id] = cand

    status_val = cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status)
    approved_at = cycle.approved_at or datetime.now(timezone.utc)
    rows: list[dict] = []
    for line in lines:
        cand = candidates.get(line.candidate_id) if line.candidate_id else None
        rows.append(
            {
                "incentive_line_id": line.id,
                "candidate_id": line.candidate_id,
                "cycle_name": cycle.name,
                "division": cycle.division,
                "incentive_month": cycle.incentive_month,
                "cycle_start_date": cycle.cycle_start_date,
                "cycle_end_date": cycle.cycle_end_date,
                "cycle_status": status_val,
                "candidate_name": line.candidate_name or (cand.candidate_name if cand else None),
                "external_candidate_id": (
                    (cand.start_id or cand.external_candidate_id) if cand else None
                ),
                "start_id": cand.start_id if cand else None,
                "start_date": cand.start_date if cand else None,
                "contract_type": cand.contract_type if cand else None,
                "candidate_source": (
                    (cand.candidate_source or cand.organization) if cand else None
                ),
                "organization": cand.organization if cand else None,
                "team": _team_label_from_candidate(cand),
                "role": line.role,
                "person": line.person,
                "incentive_type": line.incentive_type,
                "rule_applied": line.rule_applied,
                "eligible": bool(line.eligible),
                "base_incentive": line.base_incentive or Decimal("0"),
                "pro_rata_factor": line.pro_rata_factor if line.pro_rata_factor is not None else Decimal("1"),
                "amount": line.amount or Decimal("0"),
                "hours": line.hours,
                "margin": line.margin,
                "candidate_margin": cand.margin if cand else None,
                "reason": line.reason,
                "explanation_json": line.explanation_json,
                "payment_status": line.payment_status or "UNPAID",
                "crm": cand.crm if cand else None,
                "center_head": cand.center_head if cand else None,
                "associate_director": cand.associate_director if cand else None,
                "manager": cand.manager if cand else None,
                "senior_manager": cand.senior_manager if cand else None,
                "team_lead": cand.team_lead if cand else None,
                "approved_by": approved_by or cycle.created_by,
                "approved_at": approved_at,
                "comments": comments,
            }
        )
    return cycle_repository.replace_approval_results(db, cycle.id, rows)


def backfill_missing_approval_results(db: Session) -> int:
    """Snapshot any already-approved cycles that predate cycle_approval_results."""
    missing = cycle_repository.list_completed_cycles_missing_approval_results(db)
    for cycle in missing:
        snapshot_approval_results(db, cycle, approved_by=cycle.created_by)
    if missing:
        db.commit()
    return len(missing)


def _to_master_candidate(cand) -> MasterCandidate:
    return MasterCandidate(
        pk=cand.id,
        name=cand.candidate_name or "",
        external_id=cand.external_candidate_id or "",
        start_id=cand.start_id or "",
        activity_id=cand.activity_id or "",
    )


def _coordinator_issues_for_candidate(candidate, coordinators: dict) -> List[str]:
    from app.services.cycles.engines.ampcus_client import _people, _is_not_applicable

    issues: List[str] = []
    for role, person in _people(candidate).items():
        if not person or not str(person).strip():
            continue
        if _is_not_applicable(person):
            continue
        if str(person).strip().lower() not in coordinators:
            issues.append(
                f"{candidate.candidate_name} ({candidate.external_candidate_id or candidate.start_id}): "
                f"{role} '{person}' not found in Coordinator Master"
            )
    return issues


def _match_hours_rows_for_cycle(db: Session, cycle, parsed_rows: List[HoursMatchRow]):
    all_masters = [
        c for c in candidate_repository.list_all_candidates(db) if not is_seed_candidate(c)
    ]
    # Ampcus Client placement uploads list explicit candidates for the cycle.
    # Match against the full Candidate Master (minus seed rows) so records are not
    # dropped when organization is "Ampcus Inc" / "Ampcus Cyber" instead of the
    # literal string "Ampcus Tech".
    if is_ampcus_client_division(cycle.division):
        masters = all_masters
    else:
        masters = [
            c for c in all_masters if candidate_matches_division(c, cycle.division)
        ]
    master_objs = [_to_master_candidate(c) for c in masters]
    by_name = build_name_index(master_objs)
    by_id = build_id_index(master_objs)
    by_pk = {c.id: c for c in masters}

    match_rows: List[dict] = []
    matched_ids: List[int] = []
    issues: List[str] = []
    coordinator_issues: List[str] = []
    coordinators = coordinator_index(db)
    seen_coordinator_checks: set[int] = set()

    for row in parsed_rows:
        decision = match_hours_row(row, by_name, by_id)
        hours = Decimal(str(row.hours or 0))
        accepted = decision.matched
        result = (
            MatchResult.MATCHED
            if accepted
            else MatchResult.UNMATCHED
            if decision.status == UNMATCHED
            else MatchResult.REJECTED
        )
        match_rows.append(
            {
                "source_row_ref": str(row.source_row),
                "source_candidate_name": row.uploaded_name,
                "source_candidate_id": row.uploaded_id,
                "source_client": row.client,
                "hours_worked": hours,
                "candidate_id": decision.master.pk if decision.master else None,
                "match_method": decision.status,
                "match_result": result,
                "confidence": "HIGH"
                if decision.status == NAME_AND_ID
                else ("MEDIUM" if decision.status == ID_FALLBACK else "LOW"),
                "accepted": accepted,
                "notes": decision.warning or decision.reason,
            }
        )
        if accepted and decision.master:
            matched_ids.append(decision.master.pk)
            cand = by_pk.get(decision.master.pk)
            if cand and cand.id not in seen_coordinator_checks:
                seen_coordinator_checks.add(cand.id)
                coordinator_issues.extend(_coordinator_issues_for_candidate(cand, coordinators))
        elif not accepted:
            label = row.uploaded_name or row.uploaded_id or f"row {row.source_row}"
            issues.append(f"Row {row.source_row}: {label} — {decision.reason}")

    unique_matched = sorted(set(matched_ids))
    return match_rows, unique_matched, issues, coordinator_issues


def upload_hours_file(
    db: Session,
    cycle_id: int,
    filename: str,
    content: bytes,
    user: Optional[User] = None,
) -> HoursUploadOut:
    cycle = _require_cycle(db, cycle_id)
    placement_only = is_ampcus_client_division(cycle.division)
    rows = parse_hours_template(content, filename, require_hours=not placement_only)

    if placement_only or is_sambhaji_nagar_division(cycle.division):
        match_rows, matched_ids, issues, coordinator_issues = _match_hours_rows_for_cycle(db, cycle, rows)
        
        filtered_matched_ids = []
        for r in match_rows:
            if r["accepted"] and r["candidate_id"] is not None:
                if is_sambhaji_nagar_division(cycle.division):
                    if r.get("hours_worked", Decimal("0")) < Decimal("160"):
                        filtered_matched_ids.append(r["candidate_id"])
                else:
                    filtered_matched_ids.append(r["candidate_id"])
                    
        cycle_repository.replace_matches(db, cycle.id, match_rows)
        cycle_repository.sync_payment_statuses(db, cycle.id, list(set(filtered_matched_ids)))
        cycle_label = cycle.incentive_month or str(cycle.id)
        audit_service.record_event(
            db,
            action=AuditAction.FILE_UPLOAD,
            title=f"Uploaded cycle hours for {cycle_label}",
            details=(
                f"Uploaded {filename} to cycle {cycle_label}: "
                f"{len(matched_ids)} matched, {len(issues)} unmatched of {len(rows)} row(s)"
            ),
            user=user,
            metadata={
                "filename": filename,
                "cycle_id": cycle.id,
                "cycle": cycle_label,
                "matched_count": len(matched_ids),
                "unmatched_count": len(issues),
                "row_count": len(rows),
            },
            entity_type="cycle",
            entity_id=str(cycle.id),
        )
        db.commit()
        return HoursUploadOut(
            cycle_id=cycle.id,
            row_count=len(rows),
            matched_count=len(matched_ids),
            unmatched_count=len(issues),
            issues=issues,
            coordinator_issues=coordinator_issues,
            message=(
                f"Matched {len(matched_ids)} candidate(s) from {len(rows)} uploaded row(s). "
                "Review payment status before calculation."
            ),
        )

    cycle_repository.replace_matches(
        db,
        cycle.id,
        [
            {
                "source_row_ref": str(row.source_row),
                "source_candidate_name": row.uploaded_name,
                "source_candidate_id": row.uploaded_id,
                "source_client": row.client,
                "hours_worked": Decimal(str(row.hours or 0)),
                "candidate_id": None,
                "match_method": None,
                "match_result": "UNMATCHED",
                "confidence": None,
                "accepted": False,
                "notes": None,
            }
            for row in rows
        ],
    )
    cycle_label = cycle.incentive_month or str(cycle.id)
    audit_service.record_event(
        db,
        action=AuditAction.FILE_UPLOAD,
        title=f"Uploaded cycle hours for {cycle_label}",
        details=f"Uploaded {filename} to cycle {cycle_label} with {len(rows)} row(s)",
        user=user,
        metadata={
            "filename": filename,
            "cycle_id": cycle.id,
            "cycle": cycle_label,
            "row_count": len(rows),
        },
        entity_type="cycle",
        entity_id=str(cycle.id),
    )
    db.commit()
    return HoursUploadOut(
        cycle_id=cycle.id,
        row_count=len(rows),
        message=f"Stored {len(rows)} hours rows for name-first Candidate Master matching",
    )


def calculate_cycle(db: Session, cycle_id: int, user: Optional[User] = None) -> CalculateResult:
    cycle = _require_cycle(db, cycle_id)
    status_val = cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status)
    if status_val.upper() in {CycleStatus.APPROVED.value, CycleStatus.PAID.value, CycleStatus.CLOSED.value}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approved cycles cannot be recalculated",
        )
    hours_rows = _hours_rows_for_cycle(db, cycle)
    if is_ampcus_client_division(cycle.division):
        payment_rows = cycle_repository.list_payment_statuses(db, cycle.id)
        if not payment_rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Upload the placement file first — no matched candidates are linked to this cycle",
            )
    if not hours_rows and not (is_ampcus_client_division(cycle.division) or is_ampcus_inhouse_division(cycle.division)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload the filled hours template before calculating",
        )
    window = _month_window(cycle)
    drafts, stats, match_rows, validations = run_cycle_calculation(db, cycle, hours_rows, window)
    cycle_repository.replace_matches(db, cycle.id, match_rows)
    cycle_repository.replace_validations(db, cycle.id, validations)
    incentive_repository.replace_cycle_lines(
        db,
        cycle.id,
        [
            {
                "candidate_id": line.candidate_id,
                "candidate_name": line.candidate_name,
                "role": line.role,
                "person": line.person,
                "incentive_type": line.incentive_type,
                "rule_applied": line.rule_applied,
                "eligible": line.eligible,
                "base_incentive": line.base_incentive,
                "pro_rata_factor": line.pro_rata_factor,
                "amount": line.amount,
                "hours": line.hours,
                "margin": line.margin,
                "reason": line.reason,
                "explanation_json": line.explanation_json(),
                "payment_status": "UNPAID",
            }
            for line in drafts
        ],
    )
    cycle.status = CycleStatus.CALCULATED
    db.add(cycle)
    persisted = cycle_repository.list_lines(db, cycle.id)
    eligible = [line for line in persisted if line.eligible and Decimal(str(line.amount or 0)) > 0]
    total = sum((Decimal(str(line.amount or 0)) for line in eligible), Decimal("0"))
    cycle_label = cycle.incentive_month or str(cycle.id)
    audit_service.record_event(
        db,
        action=AuditAction.CALCULATION_RUN,
        title=f"Ran cycle calculation for {cycle_label}",
        details=(
            f"Calculated incentives for {cycle_label} ({cycle.division}): "
            f"{len(eligible)} eligible of {len(persisted)} line(s)"
        ),
        user=user,
        metadata={
            "cycle_id": cycle.id,
            "cycle": cycle_label,
            "division": cycle.division,
            "line_count": len(persisted),
            "eligible_line_count": len(eligible),
        },
        entity_type="cycle",
        entity_id=str(cycle.id),
    )
    db.commit()
    db.refresh(cycle)
    return CalculateResult(
        cycle=CycleOut.model_validate(cycle),
        stats=MatchStatsOut(**stats),
        line_count=len(persisted),
        eligible_line_count=len(eligible),
        total_amount=total,
        lines=[IncentiveLineOut.model_validate(line) for line in persisted],
        validations=[ValidationOut.model_validate(row) for row in cycle_repository.list_validations(db, cycle.id)],
    )


def _hours_rows_for_cycle(db: Session, cycle) -> List[HoursMatchRow]:
    matches = cycle_repository.list_matches(db, cycle.id)
    if matches:
        return [
            HoursMatchRow(
                uploaded_name=row.source_candidate_name or "",
                uploaded_id=row.source_candidate_id or "",
                client=row.source_client or "",
                hours=float(row.hours_worked or 0),
                month=cycle.incentive_month,
                source_row=int(row.source_row_ref) if str(row.source_row_ref or "").isdigit() else 0,
            )
            for row in matches
        ]
    version_id = cycle.hours_version_id
    if not version_id:
        return []
    rows = hours_repository.list_rows_for_version_month(db, version_id, cycle.incentive_month)
    if not rows:
        rows = hours_repository.list_rows_for_version(db, version_id)
    out: List[HoursMatchRow] = []
    for row in rows:
        cand = row.candidate
        out.append(
            HoursMatchRow(
                uploaded_name=row.raw_candidate_name or (cand.candidate_name if cand else ""),
                uploaded_id=(cand.start_id or cand.external_candidate_id) if cand else "",
                client=row.client or "",
                hours=float(row.hours_worked or 0),
                month=row.month_key or cycle.incentive_month,
                source_row=row.source_row or 0,
            )
        )
    return out


def _month_window(cycle) -> CycleWindow:
    if cycle.cycle_start_date and cycle.cycle_end_date:
        return CycleWindow(start=cycle.cycle_start_date, end=cycle.cycle_end_date)
    year_s, month_s = (cycle.incentive_month or "1970-01").split("-")[:2]
    year, month = int(year_s), int(month_s)
    last = calendar.monthrange(year, month)[1]
    return CycleWindow(start=date(year, month, 1), end=date(year, month, last))


def _parse_explanation(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and parsed:
        first = parsed[0]
        if isinstance(first, dict):
            return first
        if isinstance(first, str) and first.lstrip().startswith("{"):
            try:
                nested = json.loads(first)
                return nested if isinstance(nested, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _format_start_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _export_row(cycle, line, cand) -> list:
    meta = _parse_explanation(getattr(line, "explanation_json", None))
    role = line.role or ""
    coord_type = "Crm" if role == "CRM" else ("Asso Director" if role == "Associate Director" else role)
    incentive_type = "Recurring" if line.incentive_type == "RECURRING" else "One-time"
    start = ""
    if cand and cand.start_date:
        start = cand.start_date.isoformat()
    elif meta.get("start_date"):
        start = _format_start_date(meta.get("start_date"))
    contract = ""
    if cand and cand.contract_type:
        contract = cand.contract_type
    elif meta.get("contract_type"):
        contract = str(meta.get("contract_type"))
    margin_val: Any = None
    if line.margin is not None:
        margin_val = float(line.margin)
    elif cand is not None and cand.margin is not None:
        margin_val = float(cand.margin)
    elif meta.get("margin_per_hour") is not None:
        margin_val = float(meta.get("margin_per_hour"))
    ext_id = ""
    if cand:
        ext_id = cand.start_id or cand.external_candidate_id or ""
    if not ext_id:
        ext_id = str(meta.get("candidate_id") or meta.get("external_candidate_id") or "")
    source = ""
    if cand:
        source = cand.candidate_source or cand.organization or ""
    if not source:
        source = str(meta.get("candidate_source") or "")
    month = f"{cycle.incentive_month}-01" if cycle.incentive_month else ""
    return [
        line.person,
        coord_type,
        ext_id,
        line.candidate_name,
        start,
        month,
        contract,
        margin_val if margin_val is not None else "",
        float(line.hours or 0),
        int(round(float(line.amount or 0))),
        incentive_type,
        source,
    ]


def _export_row_from_snapshot(row) -> list:
    role = row.role or ""
    coord_type = "Crm" if role == "CRM" else ("Asso Director" if role == "Associate Director" else role)
    incentive_type = "Recurring" if (row.incentive_type or "").upper() == "RECURRING" else "One-time"
    start = _format_start_date(row.start_date)
    margin_val: Any = ""
    if row.margin is not None:
        margin_val = float(row.margin)
    elif row.candidate_margin is not None:
        margin_val = float(row.candidate_margin)
    month = f"{row.incentive_month}-01" if row.incentive_month else ""
    return [
        row.person,
        coord_type,
        row.start_id or row.external_candidate_id or "",
        row.candidate_name,
        start,
        month,
        row.contract_type or "",
        margin_val,
        float(row.hours or 0),
        int(round(float(row.amount or 0))),
        incentive_type,
        row.candidate_source or row.organization or "",
    ]


def export_cycle(db: Session, cycle_id: int, user: Optional[User] = None) -> StreamingResponse:
    cycle = _require_cycle(db, cycle_id)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    headers = [
        "Coordinator Name",
        "Coordinator Type",
        "Candidate ID",
        "Candidate Name",
        "Start Date",
        "Month",
        "Contract Type",
        "Margin/Finder Fees",
        "Hours/Placements",
        "Incentive Amount (INR)",
        "Incentive Type",
        "Candidate Source",
    ]
    sheet.append(headers)

    snapshots = cycle_repository.list_approval_results(db, cycle_id)
    if snapshots:
        for row in snapshots:
            if not row.eligible or Decimal(str(row.amount or 0)) <= 0:
                continue
            sheet.append(_export_row_from_snapshot(row))
    else:
        lines = cycle_repository.list_lines(db, cycle_id)
        candidates = {
            cand.id: cand
            for cand in candidate_repository.list_all_candidates(db)
        }
        for line in lines:
            if not line.eligible or Decimal(str(line.amount or 0)) <= 0:
                continue
            cand = candidates.get(line.candidate_id) if line.candidate_id else None
            sheet.append(_export_row(cycle, line, cand))

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    filename = f"approved-cycle-{cycle.incentive_month}.xlsx"
    cycle_label = cycle.incentive_month or str(cycle.id)
    audit_service.record_event(
        db,
        action=AuditAction.FILE_DOWNLOAD,
        title=f"Downloaded approved cycle Excel for {cycle_label}",
        details=f"Downloaded {filename} for cycle {cycle_label}",
        user=user,
        metadata={"cycle_id": cycle.id, "cycle": cycle_label, "filename": filename},
        entity_type="cycle",
        entity_id=str(cycle.id),
    )
    db.commit()
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _require_cycle(db: Session, cycle_id: int):
    cycle = cycle_repository.get_cycle(db, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    return cycle
