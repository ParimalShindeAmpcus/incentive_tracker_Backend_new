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
    """Return frozen approved-cycle rows for report mapping."""
    clauses = [
        "eligible = true",
        "amount > 0",
    ]
    params: Dict[str, Any] = {}

    if approved_only:
        clauses.append("cycle_status = 'APPROVED'")

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
        SELECT
            incentive_line_id AS line_id,
            person,
            role,
            candidate_name AS line_candidate_name,
            amount,
            hours,
            margin AS line_margin,
            incentive_type,
            eligible,
            cycle_id,
            cycle_name,
            division,
            incentive_month,
            cycle_status,
            external_candidate_id,
            candidate_name,
            start_date,
            contract_type,
            candidate_source,
            organization,
            candidate_margin,
            crm,
            center_head,
            associate_director,
            manager,
            senior_manager,
            team_lead,
            team
        FROM cycle_approval_results
        WHERE {where_sql}
        ORDER BY incentive_month DESC, cycle_id DESC, line_id ASC
        """
    )
    result = db.execute(sql, params)
    rows: List[Dict[str, Any]] = []
    for row in result.mappings():
        rows.append(dict(row))
    return rows
