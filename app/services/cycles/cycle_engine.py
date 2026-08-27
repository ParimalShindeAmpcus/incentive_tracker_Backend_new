"""End-to-end cycle calculation: hours rows → name-first match → Candidate Master → IncentiveLines."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.repositories.candidates import candidate_repository
from app.repositories.hours import hours_repository
from app.repositories.cycles import cycle_repository
from app.repositories.cycles.cycle_repository import (
    sn_cumulative_hours_by_candidate,
    sn_paid_recruiter_hours_by_candidate,
)
from app.repositories.entities.candidate import Candidate
from app.repositories.entities.cycle import MatchResult
from app.repositories.incentives import incentive_repository
from app.services.cycles.hours_name_matcher import (
    ID_FALLBACK,
    NAME_AND_ID,
    NAME_ID_MISMATCH,
    UNMATCHED,
    HoursMatchRow,
    MasterCandidate,
    build_id_index,
    build_name_index,
    match_hours_row,
)
from app.services.cycles.division_resolver import resolve_candidate_division
from app.services.incentives.nashik_calculator import (
    CycleWindow,
    LineDraft,
    PlacementInput,
    calculate_nashik_placement,
)
from app.services.incentives.nashik_rules import is_nashik_division, normalize_person
from app.services.cycles.engines.ampcus_client import (
    calculate_placement as calculate_ampcus_client_placement,
    coordinator_index,
    is_ampcus_client_division,
)
from app.services.incentives.recruiter_master import missing_recruiter_master_validation
from app.services.cycles.engines.ampcus_inhouse import calculate_placement as calculate_inhouse_placement, is_ampcus_inhouse_division
from app.services.cycles.cycle_candidates import resolve_candidates_for_cycle
from app.services.cycles.engines.sambhaji_nagar import calculate_placement as calculate_sambhaji_placement, is_sambhaji_nagar_division, special_average, build_sn_validations

def _to_master(cand: Candidate) -> MasterCandidate:
    return MasterCandidate(
        pk=cand.id,
        name=cand.candidate_name or "",
        external_id=cand.external_candidate_id or "",
        start_id=cand.start_id or "",
        activity_id=cand.activity_id or "",
    )


def _placement(
    cand: Candidate,
    hours: Decimal,
    window: CycleWindow,
    cumulative_hours: Optional[Decimal] = None,
) -> PlacementInput:
    end_date = cand.end_date
    return PlacementInput(
        candidate_pk=cand.id,
        external_id=cand.external_candidate_id or cand.start_id or "",
        name=cand.candidate_name,
        contract_type=cand.contract_type,
        candidate_source=cand.candidate_source,
        organization=cand.organization,
        recruiter_location=cand.recruiter_location,
        start_date=cand.start_date,
        end_date=end_date,
        margin=cand.margin,
        hours=hours,
        recruiter=cand.recruiter,
        team_lead=cand.team_lead,
        crm=cand.crm,
        manager=cand.manager,
        senior_manager=cand.senior_manager,
        associate_director=cand.associate_director,
        center_head=cand.center_head,
        avp=cand.avp,
        director=getattr(cand, "director", None),
        incentive_active=bool(cand.incentive_active),
        project_ended=end_date is not None and end_date <= window.end,
        cumulative_hours=cumulative_hours,
    )


def _ineligible_line(
    *,
    candidate_pk: Optional[int],
    name: str,
    hours: Decimal,
    reason: str,
    rule: str,
) -> LineDraft:
    return LineDraft(
        candidate_id=candidate_pk,
        candidate_name=name,
        role="Recruiter",
        person="—",
        incentive_type="RECURRING",
        rule_applied=rule,
        eligible=False,
        base_incentive=Decimal("0"),
        pro_rata_factor=Decimal("0"),
        amount=Decimal("0"),
        hours=hours,
        margin=None,
        reason=reason,
        explanation=[reason],
    )


def _nashik_employment_status(coordinators: Optional[dict]) -> Dict[str, str]:
    """Map normalize_person(name) -> ACTIVE|LEFT|NOTICE from Coordinator Master."""
    if not coordinators:
        return {}
    out: Dict[str, str] = {}
    for key, row in coordinators.items():
        status = getattr(row, "employment_status", "ACTIVE")
        status_value = str(getattr(status, "value", status) or "ACTIVE").upper()
        out[normalize_person(key)] = status_value
        full_name = getattr(row, "full_name", None)
        if full_name:
            out[normalize_person(full_name)] = status_value
        normalized = getattr(row, "normalized_name", None)
        if normalized:
            out[normalize_person(normalized)] = status_value
    return out


def run_cycle_calculation(
    db: Session,
    cycle,
    hours_rows: Sequence[HoursMatchRow],
    window: CycleWindow,
) -> Tuple[List[LineDraft], dict, List[dict], List[dict]]:
    # Ampcus Client is placement/payment/approved-markup driven.  It must not
    # require an hours import or inherit Nashik's 160-hour matching flow.
    if is_ampcus_client_division(cycle.division) or is_ampcus_inhouse_division(cycle.division):
        masters = resolve_candidates_for_cycle(db, cycle)
        payment_by_candidate = {
            row.candidate_id: row for row in cycle_repository.list_payment_statuses(db, cycle.id)
        }
        coordinators = coordinator_index(db)
        paid_keys = incentive_repository.paid_one_time_keys(db, cycle.id)
        lines = []
        pending = 0
        no_slab = 0
        for candidate in masters:
            drafts = calculate_ampcus_client_placement(candidate, cycle_end=window.end, payment=payment_by_candidate.get(candidate.id), coordinators=coordinators, paid_keys=paid_keys)
            if any(line.reason == "PAYMENT_PENDING" for line in drafts):
                pending += 1
            if any(line.reason == "MARKUP_BELOW_INCENTIVE_THRESHOLD" for line in drafts):
                no_slab += 1
            lines.extend(drafts)
        stats = {
            "total_hours_rows": len(masters), "matched_name_and_id": len(masters),
            "matched_id_fallback": 0, "name_id_mismatch": 0, "unmatched": 0,
            "inactive": sum(1 for c in masters if not c.incentive_active), "already_paid": 0,
        }
        validations = [
            {"check_key": "payment_pending", "severity": "YELLOW" if pending else "GREEN", "message": "Placements awaiting first full-month client payment", "count": pending, "details_json": None},
            {"check_key": "no_incentive_slab", "severity": "YELLOW" if no_slab else "GREEN", "message": "Placements below the client mark-up threshold", "count": no_slab, "details_json": None},
            missing_recruiter_master_validation(lines),
            {"check_key": "coordinator_ineligible", "severity": "YELLOW" if any(line.reason in {"COORDINATOR_LEFT", "COORDINATOR_ON_NOTICE"} for line in lines) else "GREEN", "message": "Coordinator on notice or left — incentive excluded", "count": sum(1 for line in lines if line.reason in {"COORDINATOR_LEFT", "COORDINATOR_ON_NOTICE"}), "details_json": None},
        ]
        return lines, stats, [], validations

    # Ampcus In-House is 90-day active tenure driven directly from Candidate Master.
    # No hours template upload required; candidates completing 90 days are automatically eligible.
    if is_ampcus_inhouse_division(cycle.division):
        masters = candidate_repository.list_all_candidates(db)
        division_masters = [c for c in masters if is_ampcus_inhouse_division(c.division)]
        if division_masters:
            masters = division_masters
        paid_keys = incentive_repository.paid_one_time_keys(db, cycle.id)
        coordinators = coordinator_index(db)
        lines = []
        not_90_days = 0
        inactive = 0
        already_paid = 0
        for candidate in masters:
            drafts = calculate_inhouse_placement(candidate, cycle_end=window.end, coordinators=coordinators, paid_keys=paid_keys)
            if any(line.reason == "INHOUSE_90_DAY_REQUIREMENT_NOT_MET" for line in drafts):
                not_90_days += 1
            if any(line.reason == "CANDIDATE_INACTIVE" for line in drafts):
                inactive += 1
            if any(line.reason == "ALREADY_PAID" for line in drafts):
                already_paid += 1
            lines.extend(drafts)
        stats = {
            "total_hours_rows": len(masters), "matched_name_and_id": len(masters),
            "matched_id_fallback": 0, "name_id_mismatch": 0, "unmatched": 0,
            "inactive": inactive, "already_paid": already_paid,
        }
        validations = [
            {"check_key": "not_90_days", "severity": "INFO" if not_90_days else "GREEN", "message": "Placements that have not reached 90 days tenure", "count": not_90_days, "details_json": None},
            {"check_key": "candidate_inactive", "severity": "YELLOW" if inactive else "GREEN", "message": "Inactive / resigned in-house candidates", "count": inactive, "details_json": None},
            missing_recruiter_master_validation(lines),
        ]
        return lines, stats, [], validations

    masters = candidate_repository.list_all_candidates(db)
    if cycle.division:
        division_masters = [c for c in masters if (c.division or "") == cycle.division]
        if division_masters:
            masters = division_masters
    master_objs = [_to_master(c) for c in masters]
    by_pk = {c.id: c for c in masters}
    by_name = build_name_index(master_objs)
    by_id = build_id_index(master_objs)

    stats = {
        "total_hours_rows": len(hours_rows),
        "matched_name_and_id": 0,
        "matched_id_fallback": 0,
        "name_id_mismatch": 0,
        "unmatched": 0,
        "inactive": 0,
        "already_paid": 0,
    }
    match_rows: List[dict] = []
    hours_by_pk: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    matched_pks: Dict[int, str] = {}
    ineligible: List[LineDraft] = []

    for row in hours_rows:
        decision = match_hours_row(row, by_name, by_id)
        hours = Decimal(str(row.hours or 0))
        method = decision.status
        accepted = decision.matched
        result = MatchResult.MATCHED if accepted else (
            MatchResult.UNMATCHED if decision.status == UNMATCHED else MatchResult.REJECTED
        )
        if decision.status == NAME_AND_ID:
            stats["matched_name_and_id"] += 1
        elif decision.status == ID_FALLBACK:
            stats["matched_id_fallback"] += 1
        elif decision.status == NAME_ID_MISMATCH:
            stats["name_id_mismatch"] += 1
        else:
            stats["unmatched"] += 1

        match_rows.append(
            {
                "source_row_ref": str(row.source_row),
                "source_candidate_name": row.uploaded_name,
                "source_candidate_id": row.uploaded_id,
                "source_client": row.client,
                "hours_worked": hours,
                "candidate_id": decision.master.pk if decision.master else None,
                "match_method": method,
                "match_result": result,
                "confidence": "HIGH" if method == NAME_AND_ID else ("MEDIUM" if method == ID_FALLBACK else "LOW"),
                "accepted": accepted,
                "notes": decision.warning or decision.reason,
            }
        )

        if not accepted:
            ineligible.append(
                _ineligible_line(
                    candidate_pk=decision.master.pk if decision.master else None,
                    name=row.uploaded_name or row.uploaded_id or "Unknown",
                    hours=hours,
                    reason=decision.reason,
                    rule=decision.status,
                )
            )
            continue

        hours_by_pk[decision.master.pk] += hours
        matched_pks[decision.master.pk] = decision.status

    paid_keys = incentive_repository.paid_one_time_keys(db, cycle.id)
    lines: List[LineDraft] = list(ineligible)
    for pk, hours in hours_by_pk.items():
        cand = by_pk[pk]
        if cand.incentive_active is False:
            stats["inactive"] += 1
            lines.append(
                _ineligible_line(
                    candidate_pk=pk,
                    name=cand.candidate_name,
                    hours=hours,
                    reason="Inactive Candidate",
                    rule="INELIGIBLE",
                )
            )
            continue
        if is_sambhaji_nagar_division(cycle.division):
            payment_by_candidate = {row.candidate_id: row for row in cycle_repository.list_payment_statuses(db, cycle.id)}
            prior_hours_map = sn_cumulative_hours_by_candidate(
                db, [pk], exclude_cycle_id=cycle.id, division=cycle.division
            )
            paid_hours_map = sn_paid_recruiter_hours_by_candidate(
                db, [pk], exclude_cycle_id=cycle.id, division=cycle.division
            )
            prior_lifetime = prior_hours_map.get(pk, Decimal("0"))
            prior_paid = paid_hours_map.get(pk, Decimal("0"))
            
            unpaid_prior = prior_lifetime - prior_paid
            if unpaid_prior < 0:
                unpaid_prior = Decimal("0")
                
            recruiter_matrix_hours = unpaid_prior + hours
            leadership_lifetime_hours = prior_lifetime + hours

            drafts = calculate_sambhaji_placement(
                cand,
                hours=hours,
                payment_status=str(getattr(payment_by_candidate.get(pk), "status", "PAYMENT_PENDING")),
                coordinators=coordinator_index(db),
                paid_keys=paid_keys,
                cycle_end=window.end,
                recruiter_matrix_hours=recruiter_matrix_hours,
                leadership_lifetime_hours=leadership_lifetime_hours,
            )
            lines.extend(drafts)
            continue
        if not is_nashik_division(cycle.division):
            lines.append(
                _ineligible_line(
                    candidate_pk=pk,
                    name=cand.candidate_name,
                    hours=hours,
                    reason=f"Division {cycle.division} calculation is not implemented in this engine",
                    rule="UNSUPPORTED_DIVISION",
                )
            )
            continue
        prior_hours = hours_repository.sum_published_hours_before_month(
            db, pk, getattr(cycle, "incentive_month", None)
        )
        drafts = calculate_nashik_placement(
            _placement(cand, hours, window, cumulative_hours=prior_hours + hours),
            window,
            paid_keys,
            employment_status=_nashik_employment_status(coordinator_index(db)),
        )
        for draft in drafts:
            payload = {
                "division": "Nashik",
                "contract_type": cand.contract_type,
                "start_date": cand.start_date.isoformat() if cand.start_date else None,
                "candidate_id": cand.start_id or cand.external_candidate_id,
                "external_candidate_id": cand.external_candidate_id,
                "candidate_name": cand.candidate_name,
                "candidate_source": cand.candidate_source or cand.organization,
                "role": draft.role,
                "person": draft.person,
                "margin_per_hour": float(cand.margin) if cand.margin is not None else None,
                "hours": float(hours),
                "benchmark_hours": 160,
                "base_incentive": float(draft.base_incentive),
                "pro_rata_factor": float(draft.pro_rata_factor),
                "final_amount": float(draft.amount),
                "eligible": draft.eligible,
                "rule": draft.rule_applied,
                "match_method": matched_pks.get(pk),
                "notes": draft.explanation,
            }
            draft.explanation = [json.dumps(payload)]
            if (not draft.eligible) and "already paid" in (draft.reason or "").lower():
                stats["already_paid"] += 1
            lines.append(draft)

    if is_sambhaji_nagar_division(cycle.division):
        lines = special_average(lines, cycle_month=cycle.incentive_month)

    validations = [
        {
            "check_key": "matched_name_and_id",
            "severity": "GREEN",
            "message": "Matched by Candidate Name + Candidate ID",
            "count": stats["matched_name_and_id"],
            "details_json": None,
        },
        {
            "check_key": "matched_id_fallback",
            "severity": "YELLOW" if stats["matched_id_fallback"] else "GREEN",
            "message": "Matched by Candidate ID because Candidate Name did not match",
            "count": stats["matched_id_fallback"],
            "details_json": None,
        },
        {
            "check_key": "name_id_mismatch",
            "severity": "RED" if stats["name_id_mismatch"] else "GREEN",
            "message": "Candidate Name matched but Candidate ID does not match Candidate Master",
            "count": stats["name_id_mismatch"],
            "details_json": None,
        },
        {
            "check_key": "unmatched",
            "severity": "RED" if stats["unmatched"] else "GREEN",
            "message": "Candidate Name and Candidate ID could not be matched with Candidate Master",
            "count": stats["unmatched"],
            "details_json": None,
        },
        {
            "check_key": "inactive",
            "severity": "YELLOW" if stats["inactive"] else "GREEN",
            "message": "Inactive Candidate",
            "count": stats["inactive"],
            "details_json": None,
        },
        missing_recruiter_master_validation(lines),
    ]
    return lines, stats, match_rows, validations


# ---------------------------------------------------------------------------
# Division-aware implementation
# ---------------------------------------------------------------------------

def run_cycle_calculation(
    db: Session,
    cycle,
    hours_rows: Sequence[HoursMatchRow],
    window: CycleWindow,
) -> Tuple[List[LineDraft], dict, List[dict], List[dict]]:
    """
    Division-aware cycle calculation:
    - Match every Hours row to Candidate Master by name-first.
    - Resolve division from Candidate Master org + recruiter location via resolver.
    - Apply cycle.division filtering BEFORE invoking the incentive engine.
    - Produce auditable per-hours-row notes (persisted in CycleHoursMatch.notes).
    """

    masters = candidate_repository.list_all_candidates(db)
    master_objs = [_to_master(c) for c in masters]
    by_pk = {c.id: c for c in masters}
    by_name = build_name_index(master_objs)
    by_id = build_id_index(master_objs)

    stats = {
        "total_hours_rows": len(hours_rows),
        "matched_name_and_id": 0,
        "matched_id_fallback": 0,
        "name_id_mismatch": 0,
        "unmatched": 0,
        "inactive": 0,
        "already_paid": 0,
    }

    match_rows: List[dict] = []
    hours_by_pk: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    included_pks: set[int] = set()
    resolved_div_by_pk: Dict[int, str] = {}
    matched_method_by_pk: Dict[int, str] = {}

    ineligible: List[LineDraft] = []

    # If payment statuses are required, load them once.
    payment_by_candidate: Dict[int, object] = {}
    if is_ampcus_client_division(cycle.division) or is_sambhaji_nagar_division(cycle.division):
        payment_by_candidate = {
            row.candidate_id: row for row in cycle_repository.list_payment_statuses(db, cycle.id)
        }

    coordinators = (
        coordinator_index(db)
        if (
            is_ampcus_client_division(cycle.division)
            or is_ampcus_inhouse_division(cycle.division)
            or is_sambhaji_nagar_division(cycle.division)
            or is_nashik_division(cycle.division)
        )
        else None
    )
    nashik_status = _nashik_employment_status(coordinators) if is_nashik_division(cycle.division) else {}
    paid_keys = incentive_repository.paid_one_time_keys(db, cycle.id)

    # 1) If hours were uploaded, match & resolve for every hours row.
    for row in hours_rows:
        decision = match_hours_row(row, by_name, by_id)
        hours = Decimal(str(row.hours or 0))

        accepted_by_matching = decision.matched
        method = decision.status
        result = MatchResult.MATCHED if accepted_by_matching else (
            MatchResult.UNMATCHED if decision.status == UNMATCHED else MatchResult.REJECTED
        )

        if decision.status == NAME_AND_ID:
            stats["matched_name_and_id"] += 1
        elif decision.status == ID_FALLBACK:
            stats["matched_id_fallback"] += 1
        elif decision.status == NAME_ID_MISMATCH:
            stats["name_id_mismatch"] += 1
        else:
            stats["unmatched"] += 1

        resolved_division: Optional[str] = None
        inclusion_status = "EXCLUDED"
        exclusion_reason: Optional[str] = None

        accepted_master = decision.master is not None
        cand_entity = by_pk.get(decision.master.pk) if accepted_master else None

        if accepted_by_matching and cand_entity:
            resolved = resolve_candidate_division(
                organization=cand_entity.organization,
                recruiter_work_location=cand_entity.recruiter_location,
                contract_type=cand_entity.contract_type,
                master_division=cand_entity.division,
            )
            resolved_division = resolved.resolved_division
            if not cand_entity.division and cycle.division:
                resolved_division = cycle.division

            resolved_div_by_pk[cand_entity.id] = resolved_division
            matched_method_by_pk[cand_entity.id] = method

            if cycle.division and resolved_division == cycle.division:
                inclusion_status = "INCLUDED"
                hours_by_pk[cand_entity.id] += hours
                included_pks.add(cand_entity.id)
            else:
                exclusion_reason = "DIVISION_MISMATCH"
                ineligible.append(
                    _ineligible_line(
                        candidate_pk=cand_entity.id,
                        name=cand_entity.candidate_name,
                        hours=hours,
                        reason=exclusion_reason,
                        rule="DIVISION_MISMATCH",
                    )
                )
        elif not accepted_by_matching and not accepted_master:
            exclusion_reason = "UNMATCHED_CANDIDATE"
            ineligible.append(
                _ineligible_line(
                    candidate_pk=None,
                    name=row.uploaded_name or row.uploaded_id or "Unknown",
                    hours=hours,
                    reason=exclusion_reason,
                    rule=decision.status,
                )
            )
        elif not accepted_by_matching and accepted_master:
            # NAME_ID_MISMATCH still points to a Candidate Master record; we
            # exclude it but keep the existing reason text for transparency.
            exclusion_reason = decision.reason
            ineligible.append(
                _ineligible_line(
                    candidate_pk=decision.master.pk,
                    name=row.uploaded_name or row.uploaded_id or "Unknown",
                    hours=hours,
                    reason=exclusion_reason,
                    rule=decision.status,
                )
            )

        match_rows.append(
            {
                "source_row_ref": str(row.source_row),
                "source_candidate_name": row.uploaded_name,
                "source_candidate_id": row.uploaded_id,
                "source_client": row.client,
                "hours_worked": hours,
                "candidate_id": decision.master.pk if decision.master else None,
                "match_method": method,
                "match_result": result,
                "confidence": "HIGH" if method == NAME_AND_ID else ("MEDIUM" if method == ID_FALLBACK else "LOW"),
                "accepted": accepted_by_matching,
                "notes": json.dumps(
                    {
                        "inclusion_status": inclusion_status,
                        "exclusion_reason": exclusion_reason,
                        "resolved_division": resolved_division,
                        "cycle_division": cycle.division,
                        "match_reason": decision.warning or decision.reason,
                    },
                    default=str,
                ),
            }
        )

    # 2) If no hours were uploaded, only Ampcus Client/In-House cycles can run.
    if not hours_rows and (is_ampcus_client_division(cycle.division) or is_ampcus_inhouse_division(cycle.division)):
        for cand in masters:
            resolved = resolve_candidate_division(
                organization=cand.organization,
                recruiter_work_location=cand.recruiter_location,
                contract_type=cand.contract_type,
                master_division=cand.division,
            )
            resolved_div_by_pk[cand.id] = resolved.resolved_division
            if cycle.division and resolved.resolved_division == cycle.division:
                included_pks.add(cand.id)

    # 3) Run the division incentive engine for included candidates only.
    lines: List[LineDraft] = list(ineligible)

    if is_ampcus_client_division(cycle.division):
        assert coordinators is not None
        pending = 0
        no_slab = 0
        for pk in included_pks:
            candidate = by_pk[pk]
            drafts = calculate_ampcus_client_placement(
                candidate,
                cycle_end=window.end,
                payment=payment_by_candidate.get(candidate.id),
                coordinators=coordinators,
                paid_keys=paid_keys,
            )
            if any(line.reason == "PAYMENT_PENDING" for line in drafts):
                pending += 1
            if any(line.reason == "MARKUP_BELOW_INCENTIVE_THRESHOLD" for line in drafts):
                no_slab += 1
            lines.extend(drafts)

        validations = [
            {
                "check_key": "payment_pending",
                "severity": "YELLOW" if pending else "GREEN",
                "message": "Placements awaiting first full-month client payment",
                "count": pending,
                "details_json": None,
            },
            {
                "check_key": "no_incentive_slab",
                "severity": "YELLOW" if no_slab else "GREEN",
                "message": "Placements below the client mark-up threshold",
                "count": no_slab,
                "details_json": None,
            },
            missing_recruiter_master_validation(lines),
        ]
        return lines, stats, match_rows, validations

    if is_ampcus_inhouse_division(cycle.division):
        assert coordinators is not None
        not_90_days = 0
        inactive = 0
        already_paid_count = 0
        for pk in included_pks:
            candidate = by_pk[pk]
            drafts = calculate_inhouse_placement(candidate, cycle_end=window.end, coordinators=coordinators, paid_keys=paid_keys)
            if any(line.reason == "INHOUSE_90_DAY_REQUIREMENT_NOT_MET" for line in drafts):
                not_90_days += 1
            if any(line.reason == "CANDIDATE_INACTIVE" for line in drafts):
                inactive += 1
            if any(line.reason == "ALREADY_PAID" for line in drafts):
                already_paid_count += 1
            lines.extend(drafts)
        stats["inactive"] = inactive
        stats["already_paid"] = already_paid_count
        validations = [
            {"check_key": "not_90_days", "severity": "INFO" if not_90_days else "GREEN", "message": "Placements that have not reached 90 days tenure", "count": not_90_days, "details_json": None},
            {"check_key": "candidate_inactive", "severity": "YELLOW" if inactive else "GREEN", "message": "Inactive / resigned in-house candidates", "count": inactive, "details_json": None},
            {"check_key": "already_paid", "severity": "YELLOW" if already_paid_count else "GREEN", "message": "One-time incentives already paid in a previous cycle", "count": already_paid_count, "details_json": None},
            missing_recruiter_master_validation(lines),
        ]
        return lines, stats, match_rows, validations

    if is_sambhaji_nagar_division(cycle.division):
        assert coordinators is not None
        # Load cumulative hours from all finalized SN cycles (exclude current cycle)
        active_pks = list(hours_by_pk.keys())
        prior_hours_map = sn_cumulative_hours_by_candidate(
            db, active_pks, exclude_cycle_id=cycle.id, division=cycle.division
        )
        paid_hours_map = sn_paid_recruiter_hours_by_candidate(
            db, active_pks, exclude_cycle_id=cycle.id, division=cycle.division
        )
        for pk, hours in hours_by_pk.items():
            cand = by_pk[pk]
            if cand.incentive_active is False:
                stats["inactive"] += 1
                lines.append(
                    _ineligible_line(
                        candidate_pk=pk,
                        name=cand.candidate_name,
                        hours=hours,
                        reason="INACTIVE_CANDIDATE",
                        rule="INELIGIBLE",
                    )
                )
                continue

            prior_lifetime = prior_hours_map.get(pk, Decimal("0"))
            prior_paid = paid_hours_map.get(pk, Decimal("0"))
            
            unpaid_prior = prior_lifetime - prior_paid
            if unpaid_prior < 0:
                unpaid_prior = Decimal("0")
                
            recruiter_matrix_hours = unpaid_prior + hours
            leadership_lifetime_hours = prior_lifetime + hours

            drafts = calculate_sambhaji_placement(
                cand,
                hours=hours,
                payment_status=str(getattr(payment_by_candidate.get(pk), "status", "PAYMENT_PENDING")),
                coordinators=coordinators,
                paid_keys=paid_keys,
                cycle_end=window.end,
                recruiter_matrix_hours=recruiter_matrix_hours,
                leadership_lifetime_hours=leadership_lifetime_hours,
            )
            lines.extend(drafts)

        sn_validations = build_sn_validations(lines)
        
        return special_average(lines, cycle_month=cycle.incentive_month), stats, match_rows, [
            {
                "check_key": "matched_name_and_id",
                "severity": "GREEN",
                "message": "Matched by Candidate Name + Candidate ID",
                "count": stats["matched_name_and_id"],
                "details_json": None,
            },
            {
                "check_key": "matched_id_fallback",
                "severity": "YELLOW" if stats["matched_id_fallback"] else "GREEN",
                "message": "Matched by Candidate ID because Candidate Name did not match",
                "count": stats["matched_id_fallback"],
                "details_json": None,
            },
            {
                "check_key": "name_id_mismatch",
                "severity": "RED" if stats["name_id_mismatch"] else "GREEN",
                "message": "Candidate Name matched but Candidate ID does not match Candidate Master",
                "count": stats["name_id_mismatch"],
                "details_json": None,
            },
            {
                "check_key": "unmatched",
                "severity": "RED" if stats["unmatched"] else "GREEN",
                "message": "Candidate Name and Candidate ID could not be matched with Candidate Master",
                "count": stats["unmatched"],
                "details_json": None,
            },
            {
                "check_key": "inactive",
                "severity": "YELLOW" if stats["inactive"] else "GREEN",
                "message": "Inactive Candidate",
                "count": stats["inactive"],
                "details_json": None,
            },
            {
                "check_key": "division_filter_summary",
                "severity": "GREEN",
                "message": "Division filter inclusion/exclusion summary",
                "count": len(included_pks),
                "details_json": json.dumps(
                    {
                        "cycle_division": cycle.division,
                        "total_hours_rows": stats["total_hours_rows"],
                        "unmatched": stats["unmatched"],
                        "included_candidates": len(included_pks),
                        "excluded_division_mismatch_candidates": max(0, len(resolved_div_by_pk) - len(included_pks)),
                        "resolved_candidates": dict(__import__("collections").Counter(resolved_div_by_pk.values())),
                    },
                    default=str,
                ),
            },
        ] + sn_validations + [missing_recruiter_master_validation(lines)]

    if is_nashik_division(cycle.division):
        for pk, hours in hours_by_pk.items():
            cand = by_pk[pk]
            if cand.incentive_active is False:
                stats["inactive"] += 1
                lines.append(
                    _ineligible_line(
                        candidate_pk=pk,
                        name=cand.candidate_name,
                        hours=hours,
                        reason="INACTIVE_CANDIDATE",
                        rule="INELIGIBLE",
                    )
                )
                continue

            prior_hours = hours_repository.sum_published_hours_before_month(
                db, pk, getattr(cycle, "incentive_month", None)
            )
            cumulative_hours = prior_hours + hours
            drafts = calculate_nashik_placement(
                _placement(cand, hours, window, cumulative_hours=cumulative_hours),
                window,
                paid_keys,
                employment_status=nashik_status,
            )
            for draft in drafts:
                payload = {
                    "division": "Nashik",
                    "contract_type": cand.contract_type,
                    "start_date": cand.start_date.isoformat() if cand.start_date else None,
                    "candidate_id": cand.start_id or cand.external_candidate_id,
                    "external_candidate_id": cand.external_candidate_id,
                    "candidate_name": cand.candidate_name,
                    "candidate_source": cand.candidate_source or cand.organization,
                    "role": draft.role,
                    "person": draft.person,
                    "margin_per_hour": float(cand.margin) if cand.margin is not None else None,
                    "hours": float(hours),
                    "monthly_hours": float(hours),
                    "cumulative_hours": float(cumulative_hours),
                    "benchmark_hours": 160,
                    "base_incentive": float(draft.base_incentive),
                    "pro_rata_factor": float(draft.pro_rata_factor),
                    "final_amount": float(draft.amount),
                    "eligible": draft.eligible,
                    "rule": draft.rule_applied,
                    "match_method": matched_method_by_pk.get(pk),
                    "notes": draft.explanation,
                }
                draft.explanation = [json.dumps(payload)]
                if (not draft.eligible) and "already paid" in (draft.reason or "").lower():
                    stats["already_paid"] += 1
                lines.append(draft)

        validations = [
            {
                "check_key": "matched_name_and_id",
                "severity": "GREEN",
                "message": "Matched by Candidate Name + Candidate ID",
                "count": stats["matched_name_and_id"],
                "details_json": None,
            },
            {
                "check_key": "matched_id_fallback",
                "severity": "YELLOW" if stats["matched_id_fallback"] else "GREEN",
                "message": "Matched by Candidate ID because Candidate Name did not match",
                "count": stats["matched_id_fallback"],
                "details_json": None,
            },
            {
                "check_key": "name_id_mismatch",
                "severity": "RED" if stats["name_id_mismatch"] else "GREEN",
                "message": "Candidate Name matched but Candidate ID does not match Candidate Master",
                "count": stats["name_id_mismatch"],
                "details_json": None,
            },
            {
                "check_key": "unmatched",
                "severity": "RED" if stats["unmatched"] else "GREEN",
                "message": "Candidate Name and Candidate ID could not be matched with Candidate Master",
                "count": stats["unmatched"],
                "details_json": None,
            },
            {
                "check_key": "inactive",
                "severity": "YELLOW" if stats["inactive"] else "GREEN",
                "message": "Inactive Candidate",
                "count": stats["inactive"],
                "details_json": None,
            },
            {
                "check_key": "division_filter_summary",
                "severity": "GREEN",
                "message": "Division filter inclusion/exclusion summary",
                "count": len(included_pks),
                "details_json": json.dumps(
                    {
                        "cycle_division": cycle.division,
                        "total_hours_rows": stats["total_hours_rows"],
                        "unmatched": stats["unmatched"],
                        "included_candidates": len(included_pks),
                        "excluded_division_mismatch_candidates": max(0, len(resolved_div_by_pk) - len(included_pks)),
                        "resolved_candidates": dict(__import__("collections").Counter(resolved_div_by_pk.values())),
                    },
                    default=str,
                ),
            },
            missing_recruiter_master_validation(lines),
        ]
        return lines, stats, match_rows, validations

    # Unsupported cycle division: produce ineligible lines for included candidates.
    for pk, hours in hours_by_pk.items():
        cand = by_pk[pk]
        lines.append(
            _ineligible_line(
                candidate_pk=pk,
                name=cand.candidate_name,
                hours=hours,
                reason=f"Division {cycle.division} calculation is not implemented in this engine",
                rule="UNSUPPORTED_DIVISION",
            )
        )

    validations = [
        {
            "check_key": "matched_name_and_id",
            "severity": "GREEN",
            "message": "Matched by Candidate Name + Candidate ID",
            "count": stats["matched_name_and_id"],
            "details_json": None,
        },
        {
            "check_key": "matched_id_fallback",
            "severity": "YELLOW" if stats["matched_id_fallback"] else "GREEN",
            "message": "Matched by Candidate ID because Candidate Name did not match",
            "count": stats["matched_id_fallback"],
            "details_json": None,
        },
        {
            "check_key": "name_id_mismatch",
            "severity": "RED" if stats["name_id_mismatch"] else "GREEN",
            "message": "Candidate Name matched but Candidate ID does not match Candidate Master",
            "count": stats["name_id_mismatch"],
            "details_json": None,
        },
        {
            "check_key": "unmatched",
            "severity": "RED" if stats["unmatched"] else "GREEN",
            "message": "Candidate Name and Candidate ID could not be matched with Candidate Master",
            "count": stats["unmatched"],
            "details_json": None,
        },
        {
            "check_key": "inactive",
            "severity": "YELLOW" if stats["inactive"] else "GREEN",
            "message": "Inactive Candidate",
            "count": stats["inactive"],
            "details_json": None,
        },
        missing_recruiter_master_validation(lines),
    ]

    if is_sambhaji_nagar_division(cycle.division):
        validations.extend(build_sn_validations(lines))

    return lines, stats, match_rows, validations
