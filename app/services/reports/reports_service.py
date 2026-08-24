"""Reports service — build approved-cycle Excel-shaped rows from DB."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.reports.schemas import ReportResponse, ReportRowOut, ReportTeamsResponse
from app.repositories.reports import reports_repository


def _coordinator_type_label(role: str) -> str:
    mapping = {
        "CRM": "Crm",
        "Associate Director": "Asso Director",
        "AVP": "AVP",
        "V I C E_ P R E S I D E N T": "V I C E_ P R E S I D E N T",
        "Vice President": "V I C E_ P R E S I D E N T",
    }
    return mapping.get(role, role)


def _incentive_type_label(incentive_type: str) -> str:
    t = (incentive_type or "").upper()
    if t in {"RECURRING"}:
        return "Recurring"
    if t in {"ONE_TIME", "ONE-TIME", "ONETIME", "SPECIAL", "FULL_TIME", "MARKUP", "INHOUSE"}:
        return "One-time"
    if incentive_type in {"Recurring", "One-time"}:
        return incentive_type
    return incentive_type or ""


def _month_as_date(month_key: str) -> str:
    if month_key and len(month_key) == 7 and month_key[4] == "-":
        return f"{month_key}-01"
    return month_key or ""


def _team_label(row: Dict[str, Any]) -> str:
    crm = (row.get("crm") or "").strip()
    center_head = (row.get("center_head") or "").strip()
    associate_director = (row.get("associate_director") or "").strip()
    manager = (row.get("manager") or "").strip()
    senior_manager = (row.get("senior_manager") or "").strip()
    team_lead = (row.get("team_lead") or "").strip()

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


def _margin_or_finder(row: Dict[str, Any]) -> Decimal | str | float | int:
    if row.get("division") == "ampcusTechInhouse":
        return "N/A"
    itype = (row.get("incentive_type") or "").upper()
    line_margin = row.get("line_margin")
    cand_margin = row.get("candidate_margin")
    if itype in {"FULL_TIME", "INHOUSE"}:
        if line_margin is not None:
            return line_margin
        return "N/A"
    if line_margin is not None:
        return line_margin
    if cand_margin is not None:
        return cand_margin
    return "N/A"


def _to_row(row: Dict[str, Any]) -> ReportRowOut:
    start = row.get("start_date")
    start_str = start.isoformat() if hasattr(start, "isoformat") else (str(start) if start else "")
    amount = Decimal(str(row.get("amount") or 0)).quantize(Decimal("1"))
    hours = row.get("hours") if row.get("hours") is not None else Decimal("0")

    return ReportRowOut(
        coordinator_name=row.get("person") or "",
        coordinator_type=_coordinator_type_label(row.get("role") or ""),
        candidate_id=row.get("external_candidate_id") or "",
        candidate_name=row.get("candidate_name") or row.get("line_candidate_name") or "",
        start_date=start_str,
        month=_month_as_date(row.get("incentive_month") or ""),
        contract_type=row.get("contract_type") or "",
        margin_finder_fees=_margin_or_finder(row),
        hours_placements=hours,
        incentive_amount_inr=amount,
        incentive_type=_incentive_type_label(row.get("incentive_type") or ""),
        candidate_source=row.get("candidate_source") or row.get("organization") or "",
        team=_team_label(row),
        division=row.get("division"),
        cycle_id=row.get("cycle_id"),
        cycle_name=row.get("cycle_name"),
        incentive_month=row.get("incentive_month"),
    )


def get_report(
    db: Session,
    *,
    division: Optional[str] = None,
    team: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
) -> ReportResponse:
    raw = reports_repository.list_report_dicts(
        db,
        division=division,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
    )

    rows: List[ReportRowOut] = []
    for item in raw:
        mapped = _to_row(item)
        if team and team != "ALL":
            if _team_label(item).strip() != team.strip():
                continue
        mapped.team = "—"
        rows.append(mapped)

    total = sum((Decimal(str(r.incentive_amount_inr)) for r in rows), Decimal("0"))
    return ReportResponse(rows=rows, total_rows=len(rows), total_incentive=total)


def list_teams(
    db: Session,
    *,
    division: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
) -> ReportTeamsResponse:
    raw = reports_repository.list_report_dicts(
        db,
        division=division,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
    )
    names: Set[str] = set()
    for row in raw:
        team = _team_label(row)
        if team:
            names.add(team)
    return ReportTeamsResponse(teams=sorted(names, key=lambda s: s.lower()))
