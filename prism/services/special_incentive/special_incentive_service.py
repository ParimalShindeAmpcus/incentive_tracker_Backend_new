"""Special Incentive — Recruiter of the Month from Candidate Master."""

from __future__ import annotations

import calendar
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from prism.config import get_settings
from prism.models.special_incentive.schemas import (
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
from prism.repositories.candidates import candidate_repository
from prism.repositories.entities.candidate import Candidate
from prism.services.cycles.cycle_candidates import is_seed_candidate

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


@dataclass
class ParsedSpecialRule:
    id: int
    division: str
    rule_category: str
    rule_key: str  # "highest_placements" | "highest_margin" | custom
    role: Optional[str]
    amount: Decimal
    placement_count_min: Optional[int]
    margin_min: Optional[Decimal]
    org_key: str
    org_name: str
    award_title: str
    tie_breaker: str  # "pay_all" | "withhold" | "split"
    priority: int
    allow_stacking: bool
    is_active: bool


def _parse_special_rule(r: Any) -> ParsedSpecialRule:
    cfg = {}
    if getattr(r, "config_value", None):
        try:
            cfg = json.loads(r.config_value)
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception:
            cfg = {}

    rule_key = (getattr(r, "rule_key", None) or "").strip().lower()
    if not rule_key:
        if "margin" in (getattr(r, "description", None) or "").lower():
            rule_key = CATEGORY_MARGIN
        else:
            rule_key = CATEGORY_PLACEMENTS

    org_key = cfg.get("org_key")
    org_name = cfg.get("org_name")
    if not org_key or not org_name:
        desc = (getattr(r, "description", None) or "").lower()
        if "bravens" in desc:
            org_key = "bravens_inc"
            org_name = "Bravens Inc"
        else:
            org_key = "ampcus_inc"
            org_name = "Ampcus Inc"

    award_title = cfg.get("award_title")
    if not award_title:
        if rule_key == CATEGORY_MARGIN:
            award_title = "Highest margin for a candidate, by recruiter"
        else:
            award_title = "Highest placements in a month by a recruiter"

    tie_breaker = cfg.get("tie_breaker", "pay_all")
    if tie_breaker not in ("pay_all", "withhold", "split"):
        tie_breaker = "pay_all"

    priority = cfg.get("priority")
    if priority is None:
        priority = 1 if rule_key == CATEGORY_PLACEMENTS else 2

    allow_stacking = cfg.get("allow_stacking", True)
    amount = Decimal(str(r.amount)) if getattr(r, "amount", None) is not None else SPECIAL_INCENTIVE_AMOUNT

    return ParsedSpecialRule(
        id=r.id,
        division=r.division,
        rule_category=r.rule_category,
        rule_key=rule_key,
        role=r.role,
        amount=amount,
        placement_count_min=r.placement_count_min,
        margin_min=r.margin_min,
        org_key=org_key,
        org_name=org_name,
        award_title=award_title,
        tie_breaker=tie_breaker,
        priority=int(priority),
        allow_stacking=bool(allow_stacking),
        is_active=bool(r.is_active),
    )


def _calculate_tie_award(amount: Decimal, tie_breaker: str, winner_count: int) -> Decimal:
    if winner_count <= 1:
        return amount
    if tie_breaker == "withhold":
        return Decimal("0")
    if tie_breaker == "split":
        return (amount / Decimal(winner_count)).quantize(Decimal("0.01"))
    return amount


def _tie_message(rule: ParsedSpecialRule, is_tie: bool, winner_count: int, award_type: str) -> Optional[str]:
    if not is_tie:
        return None
    if rule.tie_breaker == "pay_all":
        return (
            f"Tie: multiple recruiters share the {award_type}. "
            "Each tied recruiter is listed with the configured incentive."
        )
    if rule.tie_breaker == "split":
        per_person = _calculate_tie_award(rule.amount, rule.tie_breaker, winner_count)
        return (
            f"Tie: multiple recruiters share the {award_type}. "
            f"Configured bonus of ₹{rule.amount:,.0f} is split equally among {winner_count} recruiters (₹{per_person:,.0f} each)."
        )
    return f"Tie: multiple recruiters share the {award_type}. Incentive withheld until the tie is resolved (policy: withhold)."


def _compute_placements(
    rows: Sequence[Candidate],
    rule: Optional[ParsedSpecialRule] = None,
    *,
    tie_pay_all: bool = True,
    has_master_rules: bool = True,
) -> HighestPlacementsAwardOut:
    if rule is not None and not rule.is_active:
        return HighestPlacementsAwardOut(
            category=CATEGORY_PLACEMENTS,
            label=rule.award_title or "Highest Placements",
            is_tie=False,
            incentive_per_award=0,
            winners=[],
            message="Highest Placements rule is currently disabled in Incentive Rules Master.",
        )

    if rule is None and has_master_rules:
        return HighestPlacementsAwardOut(
            category=CATEGORY_PLACEMENTS,
            label="Highest Placements",
            is_tie=False,
            incentive_per_award=0,
            winners=[],
            message="Highest Placements rule is not configured for this organization.",
        )

    effective_amount = rule.amount if rule is not None else SPECIAL_INCENTIVE_AMOUNT
    effective_title = rule.award_title if rule is not None else "Highest Placements in a month by a recruiter"
    effective_tie_breaker = rule.tie_breaker if rule is not None else ("pay_all" if tie_pay_all else "withhold")
    min_count = (rule.placement_count_min or 1) if rule is not None else 1

    by_recruiter: Dict[str, List[Candidate]] = defaultdict(list)
    for c in rows:
        recruiter = _norm_recruiter(c.recruiter)
        if not recruiter:
            continue
        by_recruiter[recruiter].append(c)

    # Filter out recruiters below min count threshold
    qualifying_recruiters = {k: v for k, v in by_recruiter.items() if len(v) >= min_count}

    if not qualifying_recruiters:
        return HighestPlacementsAwardOut(
            category=CATEGORY_PLACEMENTS,
            label=effective_title,
            incentive_per_award=float(effective_amount),
            winners=[],
            message=(
                f"No eligible recruiters reached the minimum qualification threshold ({min_count} placement(s)) in Candidate Master for this month."
                if by_recruiter
                else "No eligible placements with a recruiter in Candidate Master for this month."
            ),
        )

    ranked = sorted(
        qualifying_recruiters.items(),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )
    top_count = len(ranked[0][1])
    winners_raw = [(name, cands) for name, cands in ranked if len(cands) == top_count]
    is_tie = len(winners_raw) > 1

    incentive = float(_calculate_tie_award(effective_amount, effective_tie_breaker, len(winners_raw)))

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

    mock_rule = rule or ParsedSpecialRule(
        id=0, division="special_incentive", rule_category="SPECIAL_INCENTIVE",
        rule_key=CATEGORY_PLACEMENTS, role="Recruiter", amount=effective_amount,
        placement_count_min=min_count, margin_min=None, org_key="", org_name="",
        award_title=effective_title, tie_breaker=effective_tie_breaker, priority=1,
        allow_stacking=True, is_active=True,
    )
    message = _tie_message(mock_rule, is_tie, len(winners_raw), "highest placement count")

    return HighestPlacementsAwardOut(
        category=CATEGORY_PLACEMENTS,
        label=effective_title,
        is_tie=is_tie,
        incentive_per_award=float(effective_amount),
        winners=winners,
        message=message,
    )


def _compute_margin(
    rows: Sequence[Candidate],
    rule: Optional[ParsedSpecialRule] = None,
    *,
    tie_pay_all: bool = True,
    has_master_rules: bool = True,
) -> HighestMarginAwardOut:
    if rule is not None and not rule.is_active:
        return HighestMarginAwardOut(
            category=CATEGORY_MARGIN,
            label=rule.award_title or "Highest Margin",
            is_tie=False,
            incentive_per_award=0,
            winners=[],
            message="Highest Margin rule is currently disabled in Incentive Rules Master.",
        )

    if rule is None and has_master_rules:
        return HighestMarginAwardOut(
            category=CATEGORY_MARGIN,
            label="Highest Margin",
            is_tie=False,
            incentive_per_award=0,
            winners=[],
            message="Highest Margin rule is not configured for this organization.",
        )

    effective_amount = rule.amount if rule is not None else SPECIAL_INCENTIVE_AMOUNT
    effective_title = rule.award_title if rule is not None else "Highest margin for a candidate, by recruiter"
    effective_tie_breaker = rule.tie_breaker if rule is not None else ("pay_all" if tie_pay_all else "withhold")
    min_margin = rule.margin_min if (rule is not None and rule.margin_min is not None) else Decimal("0")

    with_margin = [
        c for c in rows if c.margin is not None and Decimal(str(c.margin)) >= min_margin
    ]
    if not with_margin:
        return HighestMarginAwardOut(
            category=CATEGORY_MARGIN,
            label=effective_title,
            incentive_per_award=float(effective_amount),
            winners=[],
            message=f"No eligible candidates with C3 Margin >= ${min_margin} in Candidate Master for this month.",
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

    incentive = float(_calculate_tie_award(effective_amount, effective_tie_breaker, len(ranked)))

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

    mock_rule = rule or ParsedSpecialRule(
        id=0, division="special_incentive", rule_category="SPECIAL_INCENTIVE",
        rule_key=CATEGORY_MARGIN, role="Recruiter", amount=effective_amount,
        placement_count_min=None, margin_min=min_margin, org_key="", org_name="",
        award_title=effective_title, tie_breaker=effective_tie_breaker, priority=2,
        allow_stacking=True, is_active=True,
    )
    message = _tie_message(mock_rule, is_tie, len(ranked), "highest C3 Margin")
    if not is_tie and len(top_candidates) > 1:
        message = (
            f"Highest C3 Margin is shared by {len(top_candidates)} candidates for the same recruiter. "
            "View Details lists all of them."
        )

    return HighestMarginAwardOut(
        category=CATEGORY_MARGIN,
        label=effective_title,
        is_tie=is_tie,
        incentive_per_award=float(effective_amount),
        winners=winners,
        message=message,
    )


def get_special_incentive(db: Session, month: str) -> SpecialIncentiveResponse:
    year, mon = parse_month_key(month)
    month_key = f"{year:04d}-{mon:02d}"
    start, end = month_bounds(month_key)

    settings = get_settings()
    tie_pay_all = bool(getattr(settings, "special_incentive_tie_pay_all", True))

    # 1. Fetch Special Incentive rules from DB
    from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster

    all_db_rules = (
        db.query(IncentiveRuleMaster)
        .filter(
            IncentiveRuleMaster.division.in_(["special_incentive", "specialIncentive"]),
        )
        .all()
    )

    # Auto-seed if table has no special rules at all
    if not all_db_rules:
        from prism.services.common.seed_incentive_rules import seed_special_incentive_rules
        seeded_count = seed_special_incentive_rules(db)
        if seeded_count > 0:
            db.commit()
            all_db_rules = (
                db.query(IncentiveRuleMaster)
                .filter(
                    IncentiveRuleMaster.division.in_(["special_incentive", "specialIncentive"]),
                )
                .all()
            )

    parsed_rules: List[ParsedSpecialRule] = []
    for r in all_db_rules:
        pr = _parse_special_rule(r)
        # Determine if rule is active and falls within effective date range
        is_effective = bool(
            r.is_active
            and r.effective_from <= end
            and (r.effective_to is None or r.effective_to >= start)
        )
        pr.is_active = is_effective
        parsed_rules.append(pr)

    parsed_rules.sort(key=lambda r: (r.priority, r.id))

    # 2. Derive organizations from rules (guarantee default orgs present)
    org_map: Dict[str, Tuple[str, str]] = {}
    for k, n in SPECIAL_ORGANIZATIONS:
        org_map[k] = (k, n)
    for pr in parsed_rules:
        if pr.org_key not in org_map:
            org_map[pr.org_key] = (pr.org_key, pr.org_name)

    # 3. Eligible candidates for the month
    eligible = _eligible_for_month(db, month_key)

    orgs: List[OrganizationAwardsOut] = []
    awarded_count = 0
    awarded_amount = Decimal("0")
    total_possible_awards = 0
    total_possible_amount = Decimal("0")

    for org_key, (_, org_name) in org_map.items():
        org_rows = _filter_org(eligible, org_name)

        # Find rules for this organization
        org_rules = [r for r in parsed_rules if r.org_key == org_key]

        placements_rule = next(
            (r for r in org_rules if r.rule_key == CATEGORY_PLACEMENTS), None
        )
        margin_rule = next(
            (r for r in org_rules if r.rule_key == CATEGORY_MARGIN), None
        )

        placements = _compute_placements(
            org_rows,
            placements_rule,
            tie_pay_all=tie_pay_all,
            has_master_rules=bool(all_db_rules),
        )
        margin = _compute_margin(
            org_rows,
            margin_rule,
            tie_pay_all=tie_pay_all,
            has_master_rules=bool(all_db_rules),
        )

        # Handle multi-rule application: 2 or more rules applied together
        # Check rule stacking / exclusions if allow_stacking is explicitly False
        if placements_rule and margin_rule and placements_rule.is_active and margin_rule.is_active:
            if not margin_rule.allow_stacking or not placements_rule.allow_stacking:
                if placements_rule.priority <= margin_rule.priority:
                    top_recruiters = {w.recruiter for w in placements.winners}
                    margin.winners = [w for w in margin.winners if w.recruiter not in top_recruiters]
                else:
                    top_recruiters = {w.recruiter for w in margin.winners}
                    placements.winners = [w for w in placements.winners if w.recruiter not in top_recruiters]

        if placements_rule and placements_rule.is_active:
            total_possible_awards += 1
            total_possible_amount += placements_rule.amount
        if margin_rule and margin_rule.is_active:
            total_possible_awards += 1
            total_possible_amount += margin_rule.amount

        orgs.append(
            OrganizationAwardsOut(
                key=org_key,
                name=org_name,
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
            possible_awards=total_possible_awards,
            possible_amount=float(total_possible_amount),
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
