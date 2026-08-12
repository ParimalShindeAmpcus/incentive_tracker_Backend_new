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
