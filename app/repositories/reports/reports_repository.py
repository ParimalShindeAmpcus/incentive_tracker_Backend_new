"""Reports repository — SQL for approved incentive report rows.

Uses explicit column selects so older Postgres schemas (missing newer
candidate columns) still work for the Reports page.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_report_dicts(
    db: Session,
    *,
    division: Optional[str] = None,
    cycle_id: Optional[int] = None,
    month: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
    hod: Optional[str] = None,
    employee_name: Optional[str] = None,
    coordinator: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return frozen approved-cycle rows for report mapping."""
    report_eligibility_sql = """(
        c.role = 'Recruiter'
        OR (
            c.role != 'Recruiter'
            AND (
                (
                    c.eligible = true AND c.amount > 0
                    AND NOT EXISTS (
                        SELECT 1 FROM cycle_approval_results p
                        WHERE p.cycle_status = 'APPROVED'
                          AND (p.candidate_id = c.candidate_id OR (c.candidate_id IS NULL AND p.candidate_name = c.candidate_name))
                          AND p.role = c.role
                          AND p.eligible = true AND p.amount > 0
                          AND (p.incentive_month < c.incentive_month OR (p.incentive_month = c.incentive_month AND p.id < c.id))
                    )
                )
                OR (
                    (c.eligible = false OR c.amount <= 0)
                    AND NOT EXISTS (
                        SELECT 1 FROM cycle_approval_results p
                        WHERE p.cycle_status = 'APPROVED'
                          AND (p.candidate_id = c.candidate_id OR (c.candidate_id IS NULL AND p.candidate_name = c.candidate_name))
                          AND p.role = c.role
                          AND p.eligible = true AND p.amount > 0
                          AND (p.incentive_month <= c.incentive_month)
                    )
                )
            )
        )
    )"""
    clauses = [report_eligibility_sql]
    params: Dict[str, Any] = {}

    if approved_only:
        clauses.append("c.cycle_status = 'APPROVED'")

    if division:
        clauses.append("c.division = :division")
        params["division"] = division

    if cycle_id:
        clauses.append("c.cycle_id = :cycle_id")
        params["cycle_id"] = cycle_id

    if month:
        clauses.append("c.incentive_month = :month")
        params["month"] = month

    if from_date is not None:
        clauses.append("c.incentive_month >= :from_month")
        params["from_month"] = from_date.strftime("%Y-%m")

    if to_date is not None:
        clauses.append("c.incentive_month <= :to_month")
        params["to_month"] = to_date.strftime("%Y-%m")

    if hod:
        clauses.append("(cr.hod_name ILIKE :hod OR (cr.hod_name IS NULL AND c.center_head ILIKE :hod))")
        params["hod"] = hod.strip()

    if coordinator:
        clauses.append("c.person ILIKE :coordinator")
        params["coordinator"] = f"%{coordinator.strip()}%"

    if employee_name:
        clauses.append(
            "(c.person ILIKE :employee_name OR c.external_candidate_id ILIKE :employee_name OR c.candidate_name ILIKE :employee_name)"
        )
        params["employee_name"] = f"%{employee_name.strip()}%"

    where_sql = " AND ".join(clauses)
    sql = text(
        f"""
        SELECT
            c.incentive_line_id AS line_id,
            c.person,
            c.role,
            c.candidate_name AS line_candidate_name,
            c.amount,
            c.hours,
            c.margin AS line_margin,
            c.incentive_type,
            c.eligible,
            c.cycle_id,
            c.cycle_name,
            c.division,
            c.incentive_month,
            c.cycle_status,
            c.external_candidate_id,
            c.candidate_name,
            c.start_date,
            c.contract_type,
            c.candidate_source,
            c.organization,
            c.candidate_margin,
            c.crm,
            c.center_head,
            c.associate_director,
            c.manager,
            c.senior_manager,
            c.team_lead,
            c.team,
            c.rule_applied,
            c.base_incentive,
            c.pro_rata_factor,
            c.explanation_json,
            c.reason,
            c.payment_status,
            cr.hod_name AS cr_hod_name
        FROM cycle_approval_results c
        LEFT JOIN coordinator_records cr ON LOWER(TRIM(c.person)) = LOWER(TRIM(cr.full_name)) AND cr.is_deleted = false
        WHERE {where_sql}
        ORDER BY c.incentive_month DESC, c.cycle_id DESC, c.incentive_line_id ASC
        """
    )
    result = db.execute(sql, params)
    rows: List[Dict[str, Any]] = []
    for row in result.mappings():
        rows.append(dict(row))
    return rows
