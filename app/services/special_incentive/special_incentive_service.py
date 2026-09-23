"""Special Incentive — Recruiter of the Month from Candidate Master."""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.special_incentive.schemas import (
    HighestMarginAwardOut,
    HighestPlacementsAwardOut,
    MarginWinnerOut,
    OrganizationAwardsOut,
    PlacementWinnerOut,
    SpecialIncentiveCandidateOut,
    SpecialIncentiveDetailsResponse,
    SpecialIncentiveResponse,
    SpecialIncentiveTotalsOut,
)
from app.repositories.candidates import candidate_repository
from app.repositories.entities.candidate import Candidate
from app.services.cycles.cycle_candidates import is_seed_candidate

SPECIAL_INCENTIVE_AMOUNT = Decimal("5000")

SPECIAL_ORGANIZATIONS: Tuple[Tuple[str, str], ...] = (
    ("ampcus_inc", "Ampcus Inc"),
    ("bravens_inc", "Bravens Inc"),
)

CATEGORY_PLACEMENTS = "highest_placements"
CATEGORY_MARGIN = "highest_margin"


def _compact(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def organization_matches(candidate_org: Optional[str], target_name: str) -> bool:
    """Match Candidate Master Organization to Ampcus Inc / Bravens Inc only."""
    c = _compact(candidate_org)
    if not c:
        return False
    target = _compact(target_name)
    if target == "ampcusinc":
        if "ampcustech" in c or "inhouse" in c:
            return False
        return c == "ampcusinc" or c == "ampcus" or ("ampcus" in c and "inc" in c and "tech" not in c)
    if target == "bravensinc":
        if "bravenstech" in c:
            return False
        return c == "bravensinc" or c == "bravens" or ("bravens" in c and "inc" in c)
    return c == target


def parse_month_key(month: str) -> Tuple[int, int]:
    raw = (month or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})", raw)
    if not m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month must be YYYY-MM (e.g. 2026-09)",
        )
    year, mon = int(m.group(1)), int(m.group(2))
    if mon < 1 or mon > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid month value")
    return year, mon


def month_bounds(month: str) -> Tuple[date, date]:
    """Inclusive start / exclusive end for the selected calendar month (Start_ID month)."""
    year, mon = parse_month_key(month)
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)
    return start, end


def month_label(month: str) -> str:
    year, mon = parse_month_key(month)
    return f"{calendar.month_name[mon]} {year}"


def _candidate_display_id(c: Candidate) -> Optional[str]:
    return (
        (c.external_candidate_id or "").strip()
        or (c.start_id or "").strip()
        or (c.activity_id or "").strip()
        or None
    )


def _serialize_candidate(c: Candidate) -> SpecialIncentiveCandidateOut:
    margin = float(c.margin) if c.margin is not None else None
    return SpecialIncentiveCandidateOut(
        candidate_id=_candidate_display_id(c),
        start_id=(c.start_id or "").strip() or None,
        candidate_name=c.candidate_name or "",
        recruiter=(c.recruiter or "").strip() or None,
        organization=(c.organization or "").strip() or None,
        client=(c.client or "").strip() or None,
        start_date=c.start_date.isoformat() if c.start_date else None,
        c3_margin=margin,
        contract_type=(c.contract_type or "").strip() or None,
    )


def _eligible_for_month(db: Session, month: str) -> List[Candidate]:
    """
    Candidate Master rows for the award month.

    Business language: Start_ID month. Authoritative calendar field: start_date.
    """
    start, end = month_bounds(month)
    rows = candidate_repository.list_all_candidates(db)
    out: List[Candidate] = []
    for c in rows:
        if is_seed_candidate(c):
            continue
        if c.is_active is False or c.incentive_active is False:
            continue
        if c.start_date is None:
            continue
        if start <= c.start_date < end:
            out.append(c)
    return out


def _filter_org(rows: Iterable[Candidate], org_name: str) -> List[Candidate]:
    return [c for c in rows if organization_matches(c.organization, org_name)]


def _norm_recruiter(value: Optional[str]) -> str:
    return " ".join((value or "").split()).strip()


def _incentive_for_tie(is_tie: bool, tie_pay_all: bool) -> Decimal:
    if is_tie and not tie_pay_all:
        return Decimal("0")
    return SPECIAL_INCENTIVE_AMOUNT


def _compute_placements(
    rows: Sequence[Candidate], *, tie_pay_all: bool
) -> HighestPlacementsAwardOut:
    by_recruiter: Dict[str, List[Candidate]] = defaultdict(list)
    for c in rows:
        recruiter = _norm_recruiter(c.recruiter)
        if not recruiter:
            continue
        by_recruiter[recruiter].append(c)

    if not by_recruiter:
        return HighestPlacementsAwardOut(
            message="No eligible placements with a recruiter in Candidate Master for this month.",
        )

    ranked = sorted(
        ((name, cands) for name, cands in by_recruiter.items()),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )
    top_count = len(ranked[0][1])
    winners_raw = [(name, cands) for name, cands in ranked if len(cands) == top_count]
    is_tie = len(winners_raw) > 1
    incentive = float(_incentive_for_tie(is_tie, tie_pay_all))

    winners = [
        PlacementWinnerOut(
            recruiter=name,
            placement_count=len(cands),
            incentive=incentive,
            candidates=[
                _serialize_candidate(c)
                for c in sorted(cands, key=lambda x: (x.start_date or date.min, x.candidate_name or ""))
            ],
        )
        for name, cands in winners_raw
    ]
    message = None
    if is_tie:
        message = (
            "Tie: multiple recruiters share the highest placement count. "
            + (
                "Each tied recruiter is listed with the configured incentive."
                if tie_pay_all
                else "Incentive withheld until the tie is resolved (SPECIAL_INCENTIVE_TIE_PAY_ALL=false)."
            )
        )
    return HighestPlacementsAwardOut(
        is_tie=is_tie,
        incentive_per_award=float(SPECIAL_INCENTIVE_AMOUNT),
        winners=winners,
        message=message,
    )


def _compute_margin(rows: Sequence[Candidate], *, tie_pay_all: bool) -> HighestMarginAwardOut:
    with_margin = [c for c in rows if c.margin is not None]
    if not with_margin:
        return HighestMarginAwardOut(
            message="No eligible candidates with C3 Margin in Candidate Master for this month.",
        )

    top_margin = max(Decimal(str(c.margin)) for c in with_margin)
    top_candidates = [c for c in with_margin if Decimal(str(c.margin)) == top_margin]

    # One card per recruiter — all of that recruiter's top-margin candidates go in Details
    by_recruiter: Dict[str, List[Candidate]] = defaultdict(list)
    for c in top_candidates:
        by_recruiter[_norm_recruiter(c.recruiter) or "—"].append(c)

    ranked = sorted(
        by_recruiter.items(),
        key=lambda item: (
            item[0].casefold(),
            (item[1][0].candidate_name or "").casefold(),
        ),
    )
    is_tie = len(ranked) > 1
    incentive = float(_incentive_for_tie(is_tie, tie_pay_all))

    winners: List[MarginWinnerOut] = []
    for recruiter_name, cands in ranked:
        cands_sorted = sorted(
            cands,
            key=lambda c: ((c.candidate_name or "").casefold(), c.id),
        )
        primary = cands_sorted[0]
        serialized = [_serialize_candidate(c) for c in cands_sorted]
        winners.append(
            MarginWinnerOut(
                recruiter=recruiter_name,
                candidate_name=primary.candidate_name or "",
                candidate_id=_candidate_display_id(primary),
                start_id=(primary.start_id or "").strip() or None,
                start_date=primary.start_date.isoformat() if primary.start_date else None,
                c3_margin=float(top_margin),
                incentive=incentive,
                candidate_count=len(cands_sorted),
                candidate=serialized[0],
                candidates=serialized,
            )
        )

    message = None
    if is_tie:
        message = (
            "Tie: multiple recruiters share the highest C3 Margin. "
            + (
                "Each tied recruiter is listed once; View Details shows their qualifying candidate(s)."
                if tie_pay_all
                else "Incentive withheld until the tie is resolved (SPECIAL_INCENTIVE_TIE_PAY_ALL=false)."
            )
        )
    elif len(top_candidates) > 1:
        message = (
            f"Highest C3 Margin is shared by {len(top_candidates)} candidates for the same recruiter. "
            "View Details lists all of them."
        )

    return HighestMarginAwardOut(
        is_tie=is_tie,
        incentive_per_award=float(SPECIAL_INCENTIVE_AMOUNT),
        winners=winners,
        message=message,
    )


def get_special_incentive(db: Session, month: str) -> SpecialIncentiveResponse:
    settings = get_settings()
    tie_pay_all = bool(getattr(settings, "special_incentive_tie_pay_all", True))
    year, mon = parse_month_key(month)
    month_key = f"{year:04d}-{mon:02d}"
    eligible = _eligible_for_month(db, month_key)

    orgs: List[OrganizationAwardsOut] = []
    awarded_count = 0
    awarded_amount = Decimal("0")

    for key, name in SPECIAL_ORGANIZATIONS:
        org_rows = _filter_org(eligible, name)
        placements = _compute_placements(org_rows, tie_pay_all=tie_pay_all)
        margin = _compute_margin(org_rows, tie_pay_all=tie_pay_all)
        orgs.append(
            OrganizationAwardsOut(
                key=key,
                name=name,
                highest_placements=placements,
                highest_margin=margin,
                eligible_candidate_count=len(org_rows),
            )
        )
        for w in placements.winners:
            if w.incentive > 0:
                awarded_count += 1
                awarded_amount += Decimal(str(w.incentive))
        for w in margin.winners:
            if w.incentive > 0:
                awarded_count += 1
                awarded_amount += Decimal(str(w.incentive))

    return SpecialIncentiveResponse(
        month=month_key,
        month_label=month_label(month_key),
        incentive_amount=float(SPECIAL_INCENTIVE_AMOUNT),
        tie_pay_all=tie_pay_all,
        organizations=orgs,
        totals=SpecialIncentiveTotalsOut(
            possible_awards=4,
            possible_amount=float(SPECIAL_INCENTIVE_AMOUNT * 4),
            awarded_count=awarded_count,
            awarded_amount=float(awarded_amount),
        ),
        source="candidate_master",
    )


def get_special_incentive_details(
    db: Session,
    *,
    month: str,
    organization_key: str,
    category: str,
    recruiter: Optional[str] = None,
) -> SpecialIncentiveDetailsResponse:
    summary = get_special_incentive(db, month)
    org = next((o for o in summary.organizations if o.key == organization_key), None)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    cat = (category or "").strip().lower()
    if cat == CATEGORY_PLACEMENTS:
        award = org.highest_placements
        if not award.winners:
            return SpecialIncentiveDetailsResponse(
                month=summary.month,
                organization=org.name,
                category=cat,
                is_tie=award.is_tie,
                incentive_per_award=award.incentive_per_award,
                candidates=[],
                message=award.message or "No winners for this category.",
            )
        if recruiter:
            match = next(
                (w for w in award.winners if w.recruiter.casefold() == recruiter.strip().casefold()),
                None,
            )
            if match is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recruiter not found for this award")
            return SpecialIncentiveDetailsResponse(
                month=summary.month,
                organization=org.name,
                category=cat,
                recruiter=match.recruiter,
                is_tie=award.is_tie,
                incentive_per_award=award.incentive_per_award,
                placement_count=match.placement_count,
                candidates=match.candidates,
                message=award.message,
            )
        combined: List[SpecialIncentiveCandidateOut] = []
        for w in award.winners:
            combined.extend(w.candidates)
        return SpecialIncentiveDetailsResponse(
            month=summary.month,
            organization=org.name,
            category=cat,
            is_tie=award.is_tie,
            incentive_per_award=award.incentive_per_award,
            placement_count=award.winners[0].placement_count if award.winners else None,
            candidates=combined,
            message=award.message,
        )

    if cat == CATEGORY_MARGIN:
        award = org.highest_margin
        if not award.winners:
            return SpecialIncentiveDetailsResponse(
                month=summary.month,
                organization=org.name,
                category=cat,
                is_tie=award.is_tie,
                incentive_per_award=award.incentive_per_award,
                candidates=[],
                message=award.message or "No winners for this category.",
            )
        winners = award.winners
        if recruiter:
            winners = [w for w in winners if w.recruiter.casefold() == recruiter.strip().casefold()]
            if not winners:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recruiter not found for this award")
        combined: List[SpecialIncentiveCandidateOut] = []
        for w in winners:
            if w.candidates:
                combined.extend(w.candidates)
            else:
                combined.append(w.candidate)
        return SpecialIncentiveDetailsResponse(
            month=summary.month,
            organization=org.name,
            category=cat,
            recruiter=winners[0].recruiter if len(winners) == 1 else None,
            is_tie=award.is_tie,
            incentive_per_award=award.incentive_per_award,
            c3_margin=winners[0].c3_margin,
            candidates=combined,
            message=award.message,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="category must be highest_placements or highest_margin",
    )
