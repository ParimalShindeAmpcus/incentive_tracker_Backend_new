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
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
) -> List[Dict[str, Any]]:
    """Return flat dicts for report mapping (line + cycle + candidate fields)."""
    clauses = [
        "il.eligible = true",
        "il.amount > 0",
    ]
    params: Dict[str, Any] = {}

    if approved_only:
        clauses.append("ic.status = 'APPROVED'")

    if division:
        clauses.append("ic.division = :division")
        params["division"] = division

    if from_date is not None:
        clauses.append("ic.incentive_month >= :from_month")
        params["from_month"] = from_date.strftime("%Y-%m")

    if to_date is not None:
        clauses.append("ic.incentive_month <= :to_month")
        params["to_month"] = to_date.strftime("%Y-%m")

    where_sql = " AND ".join(clauses)
    sql = text(
        f"""
        SELECT
            il.id AS line_id,
            il.person AS person,
            il.role AS role,
            il.candidate_name AS line_candidate_name,
            il.amount AS amount,
            il.hours AS hours,
            il.margin AS line_margin,
            il.incentive_type AS incentive_type,
            ic.id AS cycle_id,
            ic.name AS cycle_name,
            ic.division AS division,
            ic.incentive_month AS incentive_month,
            c.external_candidate_id AS external_candidate_id,
            c.candidate_name AS candidate_name,
            c.start_date AS start_date,
            c.contract_type AS contract_type,
            c.candidate_source AS candidate_source,
            c.organization AS organization,
            c.margin AS candidate_margin,
            c.crm AS crm,
            c.center_head AS center_head,
            c.associate_director AS associate_director,
            c.manager AS manager,
            c.senior_manager AS senior_manager,
            c.team_lead AS team_lead
        FROM incentive_lines il
        JOIN incentive_cycles ic ON ic.id = il.cycle_id
        LEFT JOIN candidates c ON c.id = il.candidate_id
        WHERE {where_sql}
        ORDER BY ic.incentive_month DESC, ic.id DESC, il.id ASC
        """
    )
    result = db.execute(sql, params)
    rows: List[Dict[str, Any]] = []
    for row in result.mappings():
        rows.append(dict(row))
    return rows
