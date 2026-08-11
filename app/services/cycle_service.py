import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import BlockingValidationError, NotFoundError, ValidationAppError
from app.models.audit import AuditAction
from app.models.cycle import CycleStatus, MatchResult
from app.models.user import User
from app.repositories import (
    candidate_repo,
    cycle_repo,
    hours_repo,
    project_end_repo,
    recruiter_repo,
)
from app.schemas.cycle import CycleCreate, CycleUpdate
from app.services import audit_service, validation_service
from app.services.calculation.engine import IncentiveCalculationService
from app.services.matching.candidate_matcher import MatchInput, match_row
from app.services.matching.hours_aggregator import aggregate_hours_by_candidate
from app.utils.names import normalize_name
from app.utils.pagination import paginate


DEFAULT_CHECKLIST = [
    ("uploads_complete", "All source files uploaded"),
    ("matching_reviewed", "Matching reviewed"),
    ("validation_cleared", "Validation cleared"),
    ("calculation_reviewed", "Calculation reviewed"),
]


def list_cycles(db: Session, *, page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    rows = cycle_repo.list_cycles(db, offset=offset, limit=page_size)
    total = cycle_repo.count_cycles(db)
    return paginate(rows, total, page, page_size)


def get_cycle(db: Session, cycle_id: int):
    cycle = cycle_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError(f"Cycle {cycle_id} not found")
    return cycle


def create_cycle(db: Session, user: User, payload: CycleCreate):
    cycle = cycle_repo.create_cycle(
        db,
        name=payload.name,
        division=payload.division,
        incentive_month=payload.incentive_month,
        cycle_start_date=payload.cycle_start_date,
        cycle_end_date=payload.cycle_end_date,
        remarks=payload.remarks,
        candidate_version_id=payload.candidate_version_id,
        recruiter_version_id=payload.recruiter_version_id,
        hours_version_id=payload.hours_version_id,
        project_end_version_id=payload.project_end_version_id,
        created_by=user.id,
        status=CycleStatus.DRAFT,
    )
    for key, label in DEFAULT_CHECKLIST:
        cycle_repo.upsert_checklist(db, cycle.id, key, label=label, is_checked=False)
    audit_service.write(
        db,
        action=AuditAction.UPDATE,
        user_id=user.id,
        entity_type="incentive_cycle",
        entity_id=str(cycle.id),
        details=f"Created cycle {cycle.name}",
    )
    db.commit()
    db.refresh(cycle)
    return cycle


def update_cycle(db: Session, cycle_id: int, user: User, payload: CycleUpdate):
    cycle = get_cycle(db, cycle_id)
    data = payload.model_dump(exclude_unset=True)
    cycle_repo.update_cycle(db, cycle, **data)
    audit_service.write(
        db,
        action=AuditAction.UPDATE,
        user_id=user.id,
        entity_type="incentive_cycle",
        entity_id=str(cycle.id),
        details="Updated cycle",
    )
    db.commit()
    db.refresh(cycle)
    return cycle


def delete_cycle(db: Session, cycle_id: int, user: User):
    cycle = get_cycle(db, cycle_id)
    if cycle.status in {CycleStatus.APPROVED, CycleStatus.PAID}:
        raise ValidationAppError("Cannot delete an approved/paid cycle")
    cycle_repo.delete_cycle(db, cycle)
    audit_service.write(
        db,
        action=AuditAction.DELETE,
        user_id=user.id,
        entity_type="incentive_cycle",
        entity_id=str(cycle_id),
        details="Deleted cycle",
    )
    db.commit()


def _snapshot_cycle_data(db: Session, cycle) -> None:
    candidates = candidate_repo.all_for_matching(db, division=cycle.division)
    payload = {
        "candidates": [
            {
                "id": c.id,
                "external_candidate_id": c.external_candidate_id,
                "candidate_name": c.candidate_name,
                "client": c.client,
                "contract_type": c.contract_type,
                "margin": str(c.margin) if c.margin is not None else None,
                "start_date": c.start_date.isoformat() if c.start_date else None,
                "recruiter": c.recruiter,
                "team_lead": c.team_lead,
                "manager": c.manager,
                "senior_manager": c.senior_manager,
                "crm": c.crm,
                "associate_director": c.associate_director,
                "center_head": c.center_head,
                "avp": c.avp,
            }
            for c in candidates
        ]
    }
    if cycle.hours_version_id:
        payload["hours"] = [
            {
                "candidate_id": r.candidate_id,
                "hours_worked": str(r.hours_worked),
                "month_key": r.month_key,
            }
            for r in hours_repo.list_rows(db, cycle.hours_version_id)
        ]
    cycle_repo.add_snapshot(
        db,
        cycle_id=cycle.id,
        snapshot_type="CALC_INPUT",
        payload_json=json.dumps(payload),
    )


def build_matches(db: Session, cycle, *, user_id: Optional[int] = None):
    cycle_repo.clear_matches(db, cycle.id)
    candidates = candidate_repo.all_for_matching(db, division=cycle.division)
    if not cycle.hours_version_id:
        return []
    rows = hours_repo.list_rows(db, cycle.hours_version_id)
    # Also create match records from stored hours (already matched at upload)
    created = []
    for r in rows:
        created.append(
            cycle_repo.add_match(
                db,
                cycle_id=cycle.id,
                source_row_ref=str(r.source_row) if r.source_row else None,
                source_candidate_name=r.raw_candidate_name,
                source_client=r.client,
                hours_worked=r.hours_worked,
                candidate_id=r.candidate_id,
                match_method=r.match_method or "CANDIDATE_ID",
                match_result=MatchResult.MATCHED,
                confidence=r.match_confidence or "HIGH",
                accepted=True,
            )
        )
    audit_service.write(
        db,
        action=AuditAction.MATCH,
        user_id=user_id,
        entity_type="incentive_cycle",
        entity_id=str(cycle.id),
        details=f"Built {len(created)} cycle matches",
    )
    cycle.status = CycleStatus.MATCHED
    db.commit()
    return created


def calculate(db: Session, cycle_id: int, user: User):
    cycle = get_cycle(db, cycle_id)
    if not cycle_repo.list_matches(db, cycle_id):
        build_matches(db, cycle, user_id=user.id)
        cycle = get_cycle(db, cycle_id)

    validation_service.run_validation(db, cycle, user_id=user.id)
    if validation_service.has_blocking_errors(db, cycle_id):
        raise BlockingValidationError(
            "Blocking validation errors prevent calculation",
            details={"cycle_id": cycle_id},
        )

    _snapshot_cycle_data(db, cycle)
    cycle_repo.clear_lines(db, cycle_id)

    hours_map: dict[int, Decimal] = {}
    if cycle.hours_version_id:
        hours_map = aggregate_hours_by_candidate(
            [
                {"candidate_id": r.candidate_id, "hours_worked": r.hours_worked}
                for r in hours_repo.list_rows(db, cycle.hours_version_id)
            ]
        )

    project_ends = set()
    if cycle.project_end_version_id:
        project_ends = {
            r.candidate_id for r in project_end_repo.list_records(db, cycle.project_end_version_id)
        }

    status_index = {}
    if cycle.recruiter_version_id:
        for s in recruiter_repo.list_statuses(db, cycle.recruiter_version_id):
            status_index[s.normalized_name] = (
                s.status.value if hasattr(s.status, "value") else str(s.status)
            )

    candidates = candidate_repo.all_for_matching(db, division=cycle.division)
    engine = IncentiveCalculationService(db)
    total_lines = 0
    for c in candidates:
        hours = hours_map.get(c.id, Decimal("0"))
        if hours <= 0 and cycle.division not in {"ampcusTechInhouse", "fulltime"}:
            continue
        recruiter_status = status_index.get(normalize_name(c.recruiter), "ACTIVE")
        parts = engine.calculate_candidate(
            division=cycle.division,
            candidate={
                "id": c.id,
                "margin": c.margin,
                "recruiter": c.recruiter,
                "team_lead": c.team_lead,
                "manager": c.manager,
                "senior_manager": c.senior_manager,
                "crm": c.crm,
                "associate_director": c.associate_director,
                "center_head": c.center_head,
                "avp": c.avp,
                "contract_type": c.contract_type,
                "start_date": c.start_date,
            },
            hours=hours,
            recruiter_status=recruiter_status,
            project_end=c.id in project_ends,
        )
        for part in parts:
            cycle_repo.add_line(
                db,
                cycle_id=cycle.id,
                candidate_id=c.id,
                candidate_name=c.candidate_name,
                role=part["role"],
                person=part["person"] or "",
                incentive_type=part["incentive_type"],
                rule_applied=part.get("rule_applied"),
                eligible=bool(part.get("eligible")),
                base_incentive=part.get("base_incentive") or Decimal("0"),
                pro_rata_factor=part.get("pro_rata_factor") or Decimal("1"),
                amount=part.get("amount") or Decimal("0"),
                hours=hours,
                margin=c.margin,
                reason=part.get("reason"),
            )
            total_lines += 1

    # Manual adjustments as SPECIAL lines
    for adj in cycle_repo.list_adjustments(db, cycle_id):
        cycle_repo.add_line(
            db,
            cycle_id=cycle.id,
            candidate_id=adj.candidate_id,
            candidate_name=adj.candidate_name,
            role=adj.kind,
            person=adj.person or "—",
            incentive_type="SPECIAL",
            rule_applied=f"manual.{adj.kind}",
            eligible=True,
            base_incentive=adj.amount,
            pro_rata_factor=Decimal("1"),
            amount=adj.amount,
            reason=adj.notes or "Manual adjustment",
        )
        total_lines += 1

    cycle.status = CycleStatus.CALCULATED
    audit_service.write(
        db,
        action=AuditAction.CALCULATION,
        user_id=user.id,
        entity_type="incentive_cycle",
        entity_id=str(cycle.id),
        details=f"Calculated {total_lines} incentive lines",
    )
    db.commit()
    db.refresh(cycle)
    return {"cycle": cycle, "line_count": total_lines}


def summary(db: Session, cycle_id: int):
    cycle = get_cycle(db, cycle_id)
    lines = cycle_repo.list_lines(db, cycle_id)
    total_amount = sum((l.amount for l in lines if l.eligible), Decimal("0"))
    paid_amount = sum((l.amount for l in lines if l.payment_status == "PAID"), Decimal("0"))
    unmatched = len(
        [
            m
            for m in cycle_repo.list_matches(db, cycle_id)
            if m.match_result in {MatchResult.UNMATCHED, MatchResult.LOW_CONFIDENCE} and not m.accepted
        ]
    )
    blocking = len([v for v in cycle_repo.list_validations(db, cycle_id) if v.severity == "RED"])
    return {
        "cycle_id": cycle.id,
        "status": cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status),
        "total_lines": len(lines),
        "eligible_lines": sum(1 for l in lines if l.eligible),
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "unmatched_matches": unmatched,
        "blocking_validations": blocking,
    }


def update_match(db: Session, cycle_id: int, match_id: int, user: User, payload: dict):
    match = cycle_repo.get_match(db, cycle_id, match_id)
    if not match:
        raise NotFoundError(f"Match {match_id} not found")
    for k, v in payload.items():
        if v is None:
            continue
        if k == "match_result":
            match.match_result = MatchResult(v)
        else:
            setattr(match, k, v)
    if payload.get("accepted") and match.candidate_id:
        match.match_result = MatchResult.MANUAL
        match.match_method = match.match_method or "MANUAL"
    audit_service.write(
        db,
        action=AuditAction.MATCH,
        user_id=user.id,
        entity_type="cycle_hours_match",
        entity_id=str(match.id),
        details="Updated match",
    )
    db.commit()
    db.refresh(match)
    return match


def update_checklist(db: Session, cycle_id: int, key: str, user: User, *, is_checked: bool, notes: Optional[str] = None):
    get_cycle(db, cycle_id)
    item = cycle_repo.upsert_checklist(
        db,
        cycle_id,
        key,
        is_checked=is_checked,
        checked_by=user.id if is_checked else None,
        checked_at=datetime.now(timezone.utc) if is_checked else None,
        notes=notes,
    )
    db.commit()
    db.refresh(item)
    return item


def update_payment_status(db: Session, cycle_id: int, candidate_id: int, user: User, *, status: str, notes: Optional[str] = None):
    get_cycle(db, cycle_id)
    row = cycle_repo.upsert_payment_status(
        db,
        cycle_id,
        candidate_id,
        status=status,
        notes=notes,
        updated_by=user.id,
    )
    db.commit()
    db.refresh(row)
    return row
