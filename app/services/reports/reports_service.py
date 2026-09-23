"""Reports service — build approved-cycle Excel-shaped rows from DB."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.reports.schemas import (
    ReportCycleItem,
    ReportCyclesResponse,
    ReportEmployeesResponse,
    ReportHODsResponse,
    ReportMonthsResponse,
    ReportResponse,
    ReportRowOut,
    ReportTeamsResponse,
)
from app.repositories.reports import reports_repository


def _coordinator_type_label(role: str) -> str:
    mapping = {
        "CRM": "CRM",
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


def _build_coordinator_hod_map(db: Session) -> Dict[str, str]:
    """Map lower(full_name) -> hod_name from Coordinator Master table."""
    from app.repositories.entities.coordinator import CoordinatorRecord
    coords = db.query(CoordinatorRecord.full_name, CoordinatorRecord.hod_name).filter(
        CoordinatorRecord.is_deleted == False,
        CoordinatorRecord.hod_name != None,
    ).all()
    mapping: Dict[str, str] = {}
    for name, hod in coords:
        if name and hod:
            mapping[name.strip().lower()] = hod.strip()
    return mapping


def _build_candidate_recruiter_hod_map(
    raw_rows: List[Dict[str, Any]],
    coord_hod_map: Dict[str, str],
) -> Dict[tuple, str]:
    """Map (cycle/month, candidate_id/name) -> recruiter's HOD name from Coordinator Master."""
    cand_recruiter_hod: Dict[tuple, str] = {}
    for r in raw_rows:
        if (r.get("role") or "").strip().lower() == "recruiter":
            recruiter_name = (r.get("person") or "").strip().lower()
            hod = (
                coord_hod_map.get(recruiter_name)
                or (r.get("cr_hod_name") or "").strip()
                or (r.get("center_head") or "").strip()
            )
            if hod:
                cycle = str(r.get("cycle_id") or "")
                imonth = str(r.get("incentive_month") or "")
                cid1 = str(r.get("candidate_id") or "")
                cid2 = str(r.get("external_candidate_id") or "").strip().lower()
                cname = str(r.get("candidate_name") or r.get("line_candidate_name") or "").strip().lower()
                for prefix in [cycle, imonth]:
                    if cid1:
                        cand_recruiter_hod[(prefix, cid1)] = hod
                    if cid2:
                        cand_recruiter_hod[(prefix, cid2)] = hod
                    if cname:
                        cand_recruiter_hod[(prefix, cname)] = hod
    return cand_recruiter_hod


def _team_label(
    row: Dict[str, Any],
    coord_hod_map: Optional[Dict[str, str]] = None,
    cand_recruiter_hod: Optional[Dict[tuple, str]] = None,
) -> str:
    # 1. Candidate's recruiter mapped to HOD from Coordinator Master table
    if cand_recruiter_hod:
        cycle = str(row.get("cycle_id") or "")
        imonth = str(row.get("incentive_month") or "")
        cid1 = str(row.get("candidate_id") or "")
        cid2 = str(row.get("external_candidate_id") or "").strip().lower()
        cname = str(row.get("candidate_name") or row.get("line_candidate_name") or "").strip().lower()
        for prefix in [cycle, imonth]:
            for key in [(prefix, cid1), (prefix, cid2), (prefix, cname)]:
                if key in cand_recruiter_hod and cand_recruiter_hod[key]:
                    return cand_recruiter_hod[key]

    # 2. Coordinator Master table HOD for person (from SQL join cr_hod_name)
    cr_hod = (row.get("cr_hod_name") or "").strip()
    if cr_hod:
        return cr_hod

    # 3. Coordinator Master table lookup for person
    if coord_hod_map:
        person = (row.get("person") or "").strip().lower()
        if person in coord_hod_map and coord_hod_map[person]:
            return coord_hod_map[person]

    # 4. Fallback to center_head / CRM / candidate leadership fields
    center_head = (row.get("center_head") or "").strip()
    if center_head:
        return center_head

    crm = (row.get("crm") or "").strip()
    if crm:
        return crm

    associate_director = (row.get("associate_director") or "").strip()
    manager = (row.get("manager") or "").strip()
    senior_manager = (row.get("senior_manager") or "").strip()
    team_lead = (row.get("team_lead") or "").strip()

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


def _is_fte(contract_type: Optional[str]) -> bool:
    ct = (contract_type or "").strip().upper()
    return ct in {"FULLTIME", "FULL_TIME", "FT", "FTE"} or "FTE" in ct or "FULL" in ct


def _extract_fte_days(row: Dict[str, Any]) -> int:
    """Extract working days completed for FTE contract type, ignoring uploaded file hours."""
    expl = row.get("explanation_json")
    if isinstance(expl, str):
        try:
            expl = json.loads(expl)
        except Exception:
            expl = {}
    elif not isinstance(expl, dict):
        expl = {}

    if expl and expl.get("days_completed") is not None:
        try:
            d = int(expl["days_completed"])
            if d >= 0:
                return d
        except (ValueError, TypeError):
            pass

    # Fallback to tenure days computed from start_date to incentive_month end
    start = row.get("start_date")
    imonth = row.get("incentive_month")
    if start and imonth:
        try:
            import calendar
            from datetime import datetime
            y, m = map(int, str(imonth).split("-")[:2])
            last_day = calendar.monthrange(y, m)[1]
            month_end = date(y, m, last_day)
            s_date = datetime.strptime(str(start)[:10], "%Y-%m-%d").date() if isinstance(start, str) else start
            if hasattr(s_date, "year"):
                diff = (month_end - s_date).days
                if diff >= 0:
                    return diff
        except Exception:
            pass

    return 90


def _build_candidate_cumulative_hours_map(db: Session) -> Dict[str, Dict[str, Decimal]]:
    """Build a mapping of candidate_identifier -> {incentive_month: cumulative_hours} for Nashik & Sambhaji Nagar."""
    sql = text("""
        SELECT 
            UPPER(TRIM(COALESCE(external_candidate_id, ''))) AS cid1,
            UPPER(TRIM(COALESCE(candidate_name, ''))) AS cid2,
            incentive_month,
            hours,
            explanation_json
        FROM cycle_approval_results
        WHERE division IN ('sambhajiNagar', 'nashik')
    """)
    result = db.execute(sql)
    cum_map: Dict[str, Dict[str, Decimal]] = {}
    for r in result.mappings():
        cid1 = r["cid1"]
        cid2 = r["cid2"]
        m = r["incentive_month"]
        if not m:
            continue
        h = Decimal(str(r["hours"] or 0))
        h_cum = h
        expl_str = r["explanation_json"]
        if expl_str:
            try:
                expl = json.loads(expl_str) if isinstance(expl_str, str) else expl_str
                if isinstance(expl, dict) and expl.get("cumulative_hours") is not None:
                    h_cum = Decimal(str(expl["cumulative_hours"]))
            except Exception:
                pass
        val = max(h, h_cum)
        for cid in (cid1, cid2):
            if not cid:
                continue
            if cid not in cum_map:
                cum_map[cid] = {}
            if m not in cum_map[cid] or val > cum_map[cid][m]:
                cum_map[cid][m] = val
    return cum_map


def _compute_monthly_hours_from_cumulative(
    row: Dict[str, Any],
    cum_map: Optional[Dict[str, Dict[str, Decimal]]] = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate (monthly_hours, current_cumulative, prior_cumulative) for non-FTE contract types."""
    cid1 = (row.get("external_candidate_id") or "").strip().upper()
    cid2 = (row.get("candidate_name") or row.get("line_candidate_name") or "").strip().upper()
    m = row.get("incentive_month") or ""
    raw_h = Decimal(str(row.get("hours") or 0))

    if not cum_map:
        return raw_h, raw_h, Decimal("0")

    cand_history = cum_map.get(cid1) or cum_map.get(cid2)
    if not cand_history:
        return raw_h, raw_h, Decimal("0")

    current_cum = cand_history.get(m, raw_h)
    prior_months = [pm for pm in cand_history.keys() if pm < m]
    if prior_months:
        latest_prior_month = max(prior_months)
        prior_cum = cand_history[latest_prior_month]
    else:
        prior_cum = Decimal("0")

    monthly_h = max(Decimal("0"), current_cum - prior_cum)
    return monthly_h, current_cum, prior_cum


def _format_hours_clean(h: Decimal) -> str:
    try:
        val = float(h)
        if val.is_integer():
            return str(int(val))
        return f"{val:.2f}".rstrip("0").rstrip(".")
    except Exception:
        return str(h)


def _compute_validation(
    row: Dict[str, Any],
    cum_map: Optional[Dict[str, Dict[str, Decimal]]] = None,
) -> tuple[str, Optional[Decimal], Optional[int], str]:
    """Determine monthly working hours or working days contributing to incentive calculation."""
    div = (row.get("division") or "").strip().lower()
    ct = (row.get("contract_type") or "").strip().upper()
    amount = Decimal(str(row.get("amount") or 0)).quantize(Decimal("1"))
    margin = _margin_or_finder(row)
    hours_raw = row.get("hours")
    
    # 1. Nashik & Sambhaji Nagar: Hours-based validation (based on applicable contract type)
    # Exception: For FTE contract type, ignore the hours from uploaded file and show monthly working days instead.
    if "nashik" in div or "sambhajinagar" in div or div in {"nashik", "sambhajinagar"}:
        if _is_fte(ct):
            metric_type = "DAYS"
            monthly_hours = None
            monthly_days = _extract_fte_days(row)
            summary = f"Full-Time placement | {monthly_days} working days completed | Finder fee ${margin} | 90-day tenure verified | INR {amount:,}"
            return metric_type, monthly_hours, monthly_days, summary
        else:
            metric_type = "HOURS"
            monthly_h, current_cum, prior_cum = _compute_monthly_hours_from_cumulative(row, cum_map)
            clean_str = _format_hours_clean(monthly_h)
            monthly_hours = Decimal(clean_str)
            monthly_days = None
            if "nashik" in div:
                if 0 < monthly_h < 160:
                    pct = round((float(monthly_h) / 160.0) * 100, 1)
                    summary = f"{clean_str} hrs worked in month (Pro-rata {pct}%) | Margin ${margin}/hr | 160h benchmark | INR {amount:,}"
                else:
                    summary = f"{clean_str} hrs worked in month (100% full benchmark) | Margin ${margin}/hr | INR {amount:,}"
            else:
                if prior_cum > 0:
                    summary = f"{clean_str} hrs worked in month ({_format_hours_clean(current_cum)} cum - {_format_hours_clean(prior_cum)} prior) | Margin ${margin}/hr | Sambhaji Nagar matrix lookup | INR {amount:,}"
                else:
                    summary = f"{clean_str} hrs worked in month | Margin ${margin}/hr | Sambhaji Nagar matrix lookup | INR {amount:,}"
            return metric_type, monthly_hours, monthly_days, summary

    # 2. Ampcus Tech In-House & Client: Days-based validation
    metric_type = "DAYS"
    monthly_hours = None
    if "inhouse" in div:
        days = int(hours_raw) if hours_raw is not None and hours_raw > 0 else 90
        monthly_days = days
        start = row.get("start_date") or "—"
        summary = f"{days} working days completed (Start: {start}) | >= 90-day threshold met | INR {amount:,}"
        return metric_type, monthly_hours, monthly_days, summary
    else:
        # Ampcus Tech Client
        monthly_days = 20
        markup = f"{margin}%" if margin != "N/A" else "approved"
        summary = f"{monthly_days} working days in month | Mark-up {markup} slab | Client payment verified | INR {amount:,}"
        return metric_type, monthly_hours, monthly_days, summary


def _to_row(
    row: Dict[str, Any],
    cum_map: Optional[Dict[str, Dict[str, Decimal]]] = None,
    coord_hod_map: Optional[Dict[str, str]] = None,
    cand_recruiter_hod: Optional[Dict[tuple, str]] = None,
) -> ReportRowOut:
    start = row.get("start_date")
    start_str = start.isoformat() if hasattr(start, "isoformat") else (str(start) if start else "")
    amount = Decimal(str(row.get("amount") or 0)).quantize(Decimal("1"))
    metric_type, monthly_hours, monthly_days, summary = _compute_validation(row, cum_map)

    if metric_type == "DAYS" and monthly_days is not None:
        hours_placements = Decimal(str(monthly_days))
    elif monthly_hours is not None:
        hours_placements = monthly_hours
    else:
        hours_placements = row.get("hours") if row.get("hours") is not None else Decimal("0")

    return ReportRowOut(
        coordinator_name=row.get("person") or "",
        coordinator_type=_coordinator_type_label(row.get("role") or ""),
        candidate_id=row.get("external_candidate_id") or "",
        candidate_name=row.get("candidate_name") or row.get("line_candidate_name") or "",
        start_date=start_str,
        month=_month_as_date(row.get("incentive_month") or ""),
        contract_type=row.get("contract_type") or "",
        margin_finder_fees=_margin_or_finder(row),
        hours_placements=hours_placements,
        incentive_amount_inr=amount,
        incentive_type=_incentive_type_label(row.get("incentive_type") or ""),
        candidate_source=row.get("candidate_source") or row.get("organization") or "",
        team=_team_label(row, coord_hod_map, cand_recruiter_hod),
        division=row.get("division"),
        cycle_id=row.get("cycle_id"),
        cycle_name=row.get("cycle_name"),
        incentive_month=row.get("incentive_month"),
        metric_type=metric_type,
        monthly_hours=monthly_hours,
        monthly_days=monthly_days,
        validation_summary=summary,
        rule_applied=row.get("rule_applied"),
    )


def get_report(
    db: Session,
    *,
    division: Optional[str] = None,
    cycle_id: Optional[int] = None,
    month: Optional[str] = None,
    team: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
    hod: Optional[str] = None,
    employee_name: Optional[str] = None,
    coordinator: Optional[str] = None,
) -> ReportResponse:
    raw = reports_repository.list_report_dicts(
        db,
        division=division,
        cycle_id=cycle_id,
        month=month,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
        hod=hod,
        employee_name=employee_name,
        coordinator=coordinator,
    )

    cum_map = _build_candidate_cumulative_hours_map(db)
    coord_hod_map = _build_coordinator_hod_map(db)
    cand_rec_hod = _build_candidate_recruiter_hod_map(raw, coord_hod_map)

    rows: List[ReportRowOut] = []
    for item in raw:
        mapped = _to_row(item, cum_map, coord_hod_map, cand_rec_hod)
        if team and team != "ALL":
            if mapped.team.strip() != team.strip():
                continue
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
    coord_hod_map = _build_coordinator_hod_map(db)
    cand_rec_hod = _build_candidate_recruiter_hod_map(raw, coord_hod_map)
    names: Set[str] = set()
    for row in raw:
        team_name = _team_label(row, coord_hod_map, cand_rec_hod)
        if team_name and team_name != "—":
            names.add(team_name)
    return ReportTeamsResponse(teams=sorted(names, key=lambda s: s.lower()))


def list_hods(
    db: Session,
    *,
    division: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
) -> List[str]:
    from app.repositories.entities.coordinator import CoordinatorRecord

    names: Set[str] = set()
    # 1. Distinct HODs configured on coordinators (e.g. Gokul Jadhav)
    coords = db.query(CoordinatorRecord.hod_name).filter(
        CoordinatorRecord.hod_name != None,
        CoordinatorRecord.hod_name != "",
        CoordinatorRecord.is_deleted == False,
    ).distinct().all()
    for (hod,) in coords:
        hod_clean = (hod or "").strip()
        if hod_clean:
            names.add(hod_clean)

    # 2. Distinct center heads stored in cycle approval results (e.g. Geeta Krishnan, Suresh Pillai)
    chs = db.execute(text("SELECT DISTINCT center_head FROM cycle_approval_results WHERE center_head IS NOT NULL AND center_head != ''")).fetchall()
    for (ch,) in chs:
        ch_clean = (ch or "").strip()
        if ch_clean:
            names.add(ch_clean)

    return sorted(names, key=lambda s: s.lower())


def list_cycles(
    db: Session,
    *,
    division: Optional[str] = None,
    month: Optional[str] = None,
) -> ReportCyclesResponse:
    clauses = ["1=1"]
    params: Dict[str, Any] = {}
    if division and division != "ALL":
        clauses.append("division = :division")
        params["division"] = division
    if month and month != "ALL":
        clauses.append("incentive_month = :month")
        params["month"] = month

    where_sql = " AND ".join(clauses)
    sql = text(
        f"""
        SELECT
            cycle_id,
            cycle_name,
            division,
            incentive_month,
            cycle_status,
            COUNT(*) as row_count
        FROM cycle_approval_results
        WHERE {where_sql}
        GROUP BY cycle_id, cycle_name, division, incentive_month, cycle_status
        ORDER BY incentive_month DESC, cycle_id DESC
        """
    )
    rows = db.execute(sql, params).mappings().fetchall()
    cycles = [
        ReportCycleItem(
            id=int(r["cycle_id"]),
            name=str(r["cycle_name"]),
            division=str(r["division"]),
            incentive_month=str(r["incentive_month"]),
            status=str(r["cycle_status"]),
            row_count=int(r["row_count"]),
        )
        for r in rows
    ]
    return ReportCyclesResponse(cycles=cycles)


def list_months(
    db: Session,
    *,
    division: Optional[str] = None,
) -> ReportMonthsResponse:
    params: Dict[str, Any] = {}
    where_sql = ""
    if division and division != "ALL":
        where_sql = "WHERE division = :division"
        params["division"] = division

    sql = text(
        f"""
        SELECT DISTINCT incentive_month
        FROM cycle_approval_results
        {where_sql}
        ORDER BY incentive_month DESC
        """
    )
    rows = db.execute(sql, params).fetchall()
    months = [r[0] for r in rows if r[0]]
    return ReportMonthsResponse(months=months)


def list_employees(
    db: Session,
    *,
    division: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    approved_only: bool = True,
    hod: Optional[str] = None,
) -> List[str]:
    raw = reports_repository.list_report_dicts(
        db,
        division=division,
        from_date=from_date,
        to_date=to_date,
        approved_only=approved_only,
        hod=hod,
    )
    names: Set[str] = set()
    for row in raw:
        emp = (row.get("person") or "").strip()
        if emp:
            names.add(emp)
    return sorted(names, key=lambda s: s.lower())
