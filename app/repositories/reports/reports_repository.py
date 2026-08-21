"""Reports repository — SQL for approved incentive report rows.

Approved-cycle reports read the frozen `cycle_approval_results` snapshot.
Non-approved (draft/calculated) reports still use `master_reports_view`.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.entities.cycle import CycleApprovalResult


def list_report_dicts(
    db: Session,
    *,
    division: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
) -> List[Dict[str, Any]]:
    """Return flat dicts for report mapping (line + cycle + candidate fields)."""
    if approved_only:
        return _list_from_approval_results(
            db,
            division=division,
            from_date=from_date,
            to_date=to_date,
        )

    clauses = [
        "eligible = true",
        "amount > 0",
    ]
    params: Dict[str, Any] = {}

    if division:
        clauses.append("division = :division")
        params["division"] = division

    if from_date is not None:
        clauses.append("incentive_month >= :from_month")
        params["from_month"] = from_date.strftime("%Y-%m")

    if to_date is not None:
        clauses.append("incentive_month <= :to_month")
        params["to_month"] = to_date.strftime("%Y-%m")

    where_sql = " AND ".join(clauses)
    sql = text(
        f"""
        SELECT *
        FROM master_reports_view
        WHERE {where_sql}
        ORDER BY incentive_month DESC, cycle_id DESC, line_id ASC
        """
    )
    result = db.execute(sql, params)
    rows: List[Dict[str, Any]] = []
    for row in result.mappings():
        rows.append(dict(row))
    return rows


def _list_from_approval_results(
    db: Session,
    *,
    division: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    q = db.query(CycleApprovalResult).filter(
        CycleApprovalResult.eligible.is_(True),
        CycleApprovalResult.amount > 0,
    )
    if division:
        q = q.filter(CycleApprovalResult.division == division)
    if from_date is not None:
        q = q.filter(CycleApprovalResult.incentive_month >= from_date.strftime("%Y-%m"))
    if to_date is not None:
        q = q.filter(CycleApprovalResult.incentive_month <= to_date.strftime("%Y-%m"))
    rows = q.order_by(
        CycleApprovalResult.incentive_month.desc(),
        CycleApprovalResult.cycle_id.desc(),
        CycleApprovalResult.id.asc(),
    ).all()
    return [_approval_result_to_report_dict(row) for row in rows]


def _approval_result_to_report_dict(row: CycleApprovalResult) -> Dict[str, Any]:
    return {
        "line_id": row.incentive_line_id or row.id,
        "person": row.person,
        "role": row.role,
        "line_candidate_name": row.candidate_name,
        "amount": row.amount,
        "hours": row.hours,
        "line_margin": row.margin,
        "incentive_type": row.incentive_type,
        "eligible": row.eligible,
        "cycle_id": row.cycle_id,
        "cycle_name": row.cycle_name,
        "division": row.division,
        "incentive_month": row.incentive_month,
        "cycle_status": row.cycle_status,
        "external_candidate_id": row.external_candidate_id or row.start_id,
        "candidate_name": row.candidate_name,
        "start_date": row.start_date,
        "contract_type": row.contract_type,
        "candidate_source": row.candidate_source,
        "organization": row.organization,
        "candidate_margin": row.candidate_margin,
        "crm": row.crm,
        "center_head": row.center_head,
        "associate_director": row.associate_director,
        "manager": row.manager,
        "senior_manager": row.senior_manager,
        "team_lead": row.team_lead,
    }
