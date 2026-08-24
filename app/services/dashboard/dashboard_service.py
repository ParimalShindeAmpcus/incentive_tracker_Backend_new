"""Dashboard service — metrics, division cards, recent cycles."""

from calendar import month_abbr
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dashboard.schemas import (
    DashboardCycleRow,
    DashboardMetrics,
    DashboardResponse,
    DivisionCardOut,
)
from app.repositories.dashboard import dashboard_repository as repo
from app.repositories.entities.cycle import CycleStatus


DISPLAY_ORDER = (
    "nashik",
    "ampcusTechInhouse",
    "ampcusTechClient",
    "sambhajiNagar",
)

DISPLAY_NAMES = {
    "nashik": "Nashik Division",
    "ampcusTechInhouse": "Ampcus Tech In-House",
    "ampcusTechClient": "Ampcus Tech (Client)",
    "sambhajiNagar": "Sambhaji Nagar Division",
}


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _short_month_label(month_key: Optional[str]) -> str:
    if not month_key or len(month_key) < 7:
        return "—"
    try:
        year = month_key[:4]
        month = int(month_key[5:7])
        return f"{month_abbr[month]} {year}"
    except (ValueError, IndexError):
        return month_key


def _next_month_key(month_key: Optional[str]) -> str:
    from datetime import date

    if month_key and len(month_key) >= 7:
        try:
            y, m = int(month_key[:4]), int(month_key[5:7])
            if m == 12:
                return f"{y + 1}-01"
            return f"{y}-{m + 1:02d}"
        except ValueError:
            pass
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def get_dashboard(
    db: Session,
    *,
    division: Optional[str] = None,
    year: Optional[str] = None,
    month: Optional[str] = None,
) -> DashboardResponse:
    all_cycles = repo.list_all_cycles_for_division_cards(db)
    filtered = repo.list_cycles_filtered(db, division=division, year=year, month=month)

    # Metrics from filtered set (matches frontend hero filter behavior)
    draft = sum(1 for c in filtered if c.status in repo.DRAFT_LIKE)
    calculated = sum(1 for c in filtered if c.status == CycleStatus.CALCULATED)
    approved_ids = [c.id for c in filtered if c.status == CycleStatus.APPROVED]
    totals = repo.incentive_totals_by_cycle(db, approved_ids)
    approved_incentive = sum((totals.get(i, Decimal("0")) for i in approved_ids), Decimal("0"))

    metrics = DashboardMetrics(
        cycles_run=len(filtered),
        in_draft=draft,
        calculated=calculated,
        approved_incentive=approved_incentive,
    )

    # Division cards from all cycles (unfiltered by year/month so cards stay stable)
    by_div: dict[str, list] = {}
    for c in all_cycles:
        by_div.setdefault(c.division, []).append(c)

    db_divisions = {d.code: d for d in repo.list_active_divisions(db)}
    # Only the 4 product divisions — ignore extras in DB (e.g. legacy "fulltime")
    ordered_codes = [c for c in DISPLAY_ORDER if c in db_divisions]

    cards: list[DivisionCardOut] = []
    for code in ordered_codes:
        rows = by_div.get(code, [])
        approved = sum(1 for c in rows if c.status == CycleStatus.APPROVED)
        active = sum(1 for c in rows if c.status == CycleStatus.CALCULATED)
        draft = sum(1 for c in rows if c.status in repo.DRAFT_LIKE)
        latest = rows[0].incentive_month if rows else None
        next_key = _next_month_key(latest)
        div = db_divisions.get(code)
        cards.append(
            DivisionCardOut(
                code=code,
                name=DISPLAY_NAMES.get(code) or (div.name if div else code),
                approved=approved,
                active=active,
                draft=draft,
                cancelled=0,
                latest_month=latest,
                latest_label=_short_month_label(latest) if latest else "—",
                next_label=_short_month_label(next_key),
            )
        )

    # Recent cycles table rows (filtered)
    recent_totals = repo.incentive_totals_by_cycle(db, [c.id for c in filtered])
    recent = [
        DashboardCycleRow(
            id=c.id,
            name=c.name,
            division=c.division,
            incentive_month=c.incentive_month,
            status=_status_value(c.status),
            total_incentive=recent_totals.get(c.id, Decimal("0")),
            cycle_start_date=c.cycle_start_date.isoformat() if c.cycle_start_date else None,
            cycle_end_date=c.cycle_end_date.isoformat() if c.cycle_end_date else None,
            created_at=c.created_at,
            approved_at=c.approved_at,
        )
        for c in filtered
    ]

    return DashboardResponse(metrics=metrics, divisions=cards, recent_cycles=recent)
