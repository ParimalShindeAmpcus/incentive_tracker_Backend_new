import json
from typing import List

from sqlalchemy.orm import Session

from app.models.audit import AuditAction
from app.models.cycle import IncentiveCycle
from app.repositories import candidate_repo, cycle_repo, hours_repo, project_end_repo, recruiter_repo
from app.services import audit_service


def run_validation(db: Session, cycle: IncentiveCycle, *, user_id: int | None = None) -> List:
    cycle_repo.clear_validations(db, cycle.id)
    results = []

    def add(key: str, severity: str, message: str, count: int = 0, details=None):
        row = cycle_repo.add_validation(
            db,
            cycle_id=cycle.id,
            check_key=key,
            severity=severity,
            message=message,
            count=count,
            details_json=json.dumps(details) if details is not None else None,
        )
        results.append(row)

    candidates = []
    if cycle.candidate_version_id:
        candidates = [
            c
            for c in candidate_repo.all_for_matching(db, division=cycle.division)
            if c.last_touched_version_id == cycle.candidate_version_id
            or c.source_version_id == cycle.candidate_version_id
        ]
        if not candidates:
            candidates = candidate_repo.all_for_matching(db, division=cycle.division)

    add("total_candidates", "GREEN", "Total candidates in scope", len(candidates))

    hours_count = 0
    if cycle.hours_version_id:
        hours_count = len(hours_repo.list_rows(db, cycle.hours_version_id))
    add(
        "hours_records",
        "GREEN" if hours_count else "YELLOW",
        "Hours records linked to cycle",
        hours_count,
    )

    matches = cycle_repo.list_matches(db, cycle.id)
    unmatched = [m for m in matches if m.match_result.value in {"UNMATCHED", "LOW_CONFIDENCE"} and not m.accepted]
    add(
        "unmatched_candidates",
        "RED" if unmatched else "GREEN",
        "Unmatched / low-confidence hours matches",
        len(unmatched),
    )

    missing_margin = [c for c in candidates if c.margin is None]
    add(
        "missing_margin",
        "RED" if missing_margin else "GREEN",
        "Candidates missing margin",
        len(missing_margin),
    )

    missing_start = [c for c in candidates if c.start_date is None]
    add(
        "missing_start_date",
        "YELLOW" if missing_start else "GREEN",
        "Candidates missing start date",
        len(missing_start),
    )

    missing_recruiter = [c for c in candidates if not c.recruiter]
    add(
        "missing_recruiter",
        "YELLOW" if missing_recruiter else "GREEN",
        "Candidates missing recruiter",
        len(missing_recruiter),
    )

    left = notice = 0
    if cycle.recruiter_version_id:
        for s in recruiter_repo.list_statuses(db, cycle.recruiter_version_id):
            val = s.status.value if hasattr(s.status, "value") else str(s.status)
            if val == "LEFT":
                left += 1
            elif val == "NOTICE":
                notice += 1
    add("recruiters_left", "YELLOW" if left else "GREEN", "Recruiters with LEFT status", left)
    add("recruiters_notice", "YELLOW" if notice else "GREEN", "Recruiters on NOTICE", notice)

    pe_count = 0
    if cycle.project_end_version_id:
        pe_count = len(project_end_repo.list_records(db, cycle.project_end_version_id))
    add("project_end_candidates", "GREEN", "Project-end records", pe_count)

    audit_service.write(
        db,
        action=AuditAction.VALIDATION,
        user_id=user_id,
        entity_type="incentive_cycle",
        entity_id=str(cycle.id),
        details=f"Validation checks={len(results)}",
    )
    db.commit()
    return results


def has_blocking_errors(db: Session, cycle_id: int) -> bool:
    return any(v.severity == "RED" for v in cycle_repo.list_validations(db, cycle_id))
