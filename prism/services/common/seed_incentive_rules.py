"""Seed all current hardcoded incentive rules into the incentive_rule_master table.

This function is idempotent — it only inserts if the table is empty.
All values exactly replicate the current hardcoded constants so that
calculation results on day-1 are byte-for-byte identical to pre-master behaviour.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from prism.repositories.incentive_rules.incentive_rules_repository import has_any_rules

logger = logging.getLogger(__name__)

# Reference date: rules that have always existed get this effective_from
EPOCH = date(2024, 1, 1)


def seed_incentive_rules(db: Session) -> None:
    """Insert all hardcoded incentive rules as initial master data.

    Guards:
      - Only runs when the table is completely empty (first startup).
      - All inserts are done in a single transaction via the caller's session.
    """
    if has_any_rules(db):
        logger.debug("incentive_rule_master already seeded — skipping.")
        return

    rows = _build_seed_rows()
    from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster

    for data in rows:
        db.add(IncentiveRuleMaster(**data))

    db.flush()
    logger.info("Seeded %d incentive rule master records.", len(rows))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(**kwargs: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "is_active": True,
        "effective_from": EPOCH,
        "effective_to": None,
        "created_by": None,
        "updated_by": None,
    }
    base.update(kwargs)
    return base


def _build_seed_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    # =========================================================================
    # NASHIK DIVISION
    # =========================================================================

    # ── Nashik Global Config ──────────────────────────────────────────────────
    nashik_config = [
        ("standard_hours", "160", "Standard hours per month for pro-rata calculation"),
        ("low_margin_threshold", "1.00", "Margin/hour threshold below which low-margin special rule applies (USD)"),
        ("low_margin_one_time_amount", "2000", "One-time INR incentive for recruiter when margin < $1/hr"),
        ("team_lead_base", "250", "Base INR per placement per 160h for Team Lead (pro-rated)"),
        ("project_end_recruiter_amount", "2000", "Flat INR for recruiter when project ends before 160h"),
        ("max_roles_per_person", "2", "Maximum eligible roles any single person can hold in a placement"),
        ("leadership_hours_requirement", "160", "Cumulative hours required before one-time leadership incentive triggers"),
    ]
    for key, val, desc in nashik_config:
        rows.append(_row(
            division="nashik",
            rule_category="GLOBAL_CONFIG",
            rule_key=key,
            config_value=val,
            description=desc,
        ))

    # ── Nashik Recruiter Margin Slabs ─────────────────────────────────────────
    # Mirrors RECRUITER_SLABS in nashik_rules.py
    nashik_slabs = [
        ("1.00", "2.00", 500),
        ("2.01", "4.00", 1000),
        ("4.01", "6.00", 1500),
        ("6.01", "8.00", 2000),
        ("8.01", "10.00", 2500),
        ("10.01", "15.00", 3500),
        ("15.01", "20.00", 4000),
        ("20.01", "30.00", 4500),
        ("30.01", "40.00", 7000),
        ("40.01", "50.00", 10000),
    ]
    for lo, hi, amt in nashik_slabs:
        rows.append(_row(
            division="nashik",
            rule_category="RECRUITER_SLAB",
            role="Recruiter",
            margin_min=Decimal(lo),
            margin_max=Decimal(hi),
            amount=Decimal(amt),
            description=f"Nashik recruiter incentive for margin ${lo}–${hi}/hr",
        ))

    # ── Nashik Leadership One-Time ────────────────────────────────────────────
    # Mirrors LEADERSHIP_ONE_TIME in nashik_rules.py
    nashik_leadership = [
        ("CRM", 1000),
        ("Manager", 1500),
        ("Senior Manager", 1500),
        ("Associate Director", 1750),
        ("Director", 1750),
        ("Center Head", 1500),
        ("AVP", 2300),
    ]
    for role, amt in nashik_leadership:
        rows.append(_row(
            division="nashik",
            rule_category="LEADERSHIP_ONE_TIME",
            role=role,
            amount=Decimal(amt),
            description=f"Nashik one-time incentive for {role} on 160h+ completion",
        ))

    # =========================================================================
    # SAMBHAJI NAGAR DIVISION
    # =========================================================================

    # ── SN Global Config ──────────────────────────────────────────────────────
    sn_config = [
        ("standard_hours", "160", "Standard hours for SN recruiter matrix bucket"),
        ("fte_finder_fee_threshold", "4500", "Finder fee amount separating below/above FTE slab (INR)"),
        ("fte_min_days", "90", "Minimum days before FTE incentive is payable"),
        ("max_roles_per_person", "2", "Maximum eligible roles per person"),
        ("special_incentive_enabled", "true", "Enable Recruiter Special Incentive Plan (Multiple Placements)"),
        ("special_min_placements", "2", "Minimum qualifying placements in same calendar month required for special incentive"),
        ("special_min_hours", "160", "Minimum cumulative hours per placement required to qualify for special incentive average"),
        ("special_evaluation_hours", "161", "Evaluation hours tier for special incentive matrix lookup (161+ hrs)"),
    ]
    for key, val, desc in sn_config:
        rows.append(_row(
            division="sambhajiNagar",
            rule_category="GLOBAL_CONFIG",
            rule_key=key,
            config_value=val,
            description=desc,
        ))

    # ── SN Recruiter Matrix (BANDS — TABLE 5) ─────────────────────────────────
    # 8 margin bands × 5 hour bands
    # hours bands: 0-40, 41-80, 81-120, 121-160, 161+
    hour_bands = [
        (Decimal("0"), Decimal("40")),
        (Decimal("41"), Decimal("80")),
        (Decimal("81"), Decimal("120")),
        (Decimal("121"), Decimal("160")),
        (Decimal("161"), Decimal("99999")),
    ]
    sn_bands = [
        ("1.00", "3.00", (500, 1000, 2000, 3000, 4000)),
        ("3.01", "5.00", (1000, 2000, 3000, 4000, 5000)),
        ("5.01", "7.00", (2000, 3000, 4000, 5000, 7000)),
        ("7.01", "10.00", (3000, 4000, 5000, 6000, 8500)),
        ("10.01", "15.00", (4000, 5000, 6000, 7000, 10000)),
        ("15.01", "20.00", (5000, 6000, 7000, 8000, 15000)),
        ("20.01", "30.00", (6000, 7000, 8000, 10000, 20000)),
        ("30.01", "50.00", (7000, 8000, 9000, 12000, 25000)),
        ("51.00", "80.00", (999, 999, 999, 999, 999)),
    ]
    hour_labels = ["0–40h", "41–80h", "81–120h", "121–160h", "161+h"]
    for m_lo, m_hi, amts in sn_bands:
        for idx, (h_lo, h_hi) in enumerate(hour_bands):
            rows.append(_row(
                division="sambhajiNagar",
                rule_category="RECRUITER_SLAB",
                role="Recruiter",
                margin_min=Decimal(m_lo),
                margin_max=Decimal(m_hi),
                hours_min=h_lo,
                hours_max=h_hi,
                amount=Decimal(amts[idx]),
                description=f"SN recruiter: margin ${m_lo}–${m_hi}, hours {hour_labels[idx]}",
            ))

    # ── SN W2/C2C Leadership (FIXED — TABLE 6) ────────────────────────────────
    sn_fixed = [
        ("Team Lead", 500),
        ("Manager", 1000),
        ("Senior Manager", 1500),
        ("CRM", 1000),
        ("Associate Director", 1750),
        ("Center Head", 1750),
        ("AVP", 1750),
        ("Director", 1000),
    ]
    for role, amt in sn_fixed:
        rows.append(_row(
            division="sambhajiNagar",
            rule_category="LEADERSHIP_ONE_TIME",
            role=role,
            amount=Decimal(amt),
            description=f"SN W2/C2C one-time for {role} on 160h cumulative",
        ))

    # ── SN FTE Leadership (FTE_FIXED — TABLE 2) ───────────────────────────────
    sn_fte_fixed = [
        ("Team Lead", 1000),
        ("Manager", 1500),
        ("CRM", 1500),
        ("Associate Director", 4000),
        ("Center Head", 4000),
        ("AVP", 4000),
        ("Director", 1500),
        ("Senior Manager", 1500),
    ]
    for role, amt in sn_fte_fixed:
        rows.append(_row(
            division="sambhajiNagar",
            rule_category="FTE_LEADERSHIP",
            role=role,
            amount=Decimal(amt),
            description=f"SN FTE one-time for {role} after 90 days",
        ))

    # ── SN / Nashik FTE Recruiter Slabs ──────────────────────────────────────
    # FTE_RECRUITER_SLABS: {False: (15000,18000,20000), True: (20000,25000,30000)}
    # placement_count_min/max encode the count bucket: 1, 2, 3+
    fte_placements = [
        (1, 1),   # 1 placement
        (2, 2),   # 2 placements
        (3, 999), # 3+ placements
    ]
    fte_amounts = {
        False: [15000, 18000, 20000],  # Below finder fee threshold
        True: [20000, 25000, 30000],   # Above finder fee threshold
    }
    finder_labels = {False: "below $4,500", True: "above $4,500"}
    placement_labels = ["1 placement", "2 placements", "3+ placements"]
    for above, amts in fte_amounts.items():
        for idx, (cnt_min, cnt_max) in enumerate(fte_placements):
            for div in ("sambhajiNagar", "nashik"):
                rows.append(_row(
                    division=div,
                    rule_category="FTE_RECRUITER_SLAB",
                    role="Recruiter",
                    finder_fee_above=above,
                    placement_count_min=cnt_min,
                    placement_count_max=cnt_max,
                    amount=Decimal(amts[idx]),
                    description=(
                        f"FTE recruiter: finder fee {finder_labels[above]}, "
                        f"{placement_labels[idx]}"
                    ),
                ))

    # Nashik FTE config (shares FTE rules with SN)
    rows.append(_row(
        division="nashik",
        rule_category="GLOBAL_CONFIG",
        rule_key="fte_finder_fee_threshold",
        config_value="4500",
        description="Finder fee threshold separating below/above FTE slab (INR)",
    ))
    rows.append(_row(
        division="nashik",
        rule_category="GLOBAL_CONFIG",
        rule_key="fte_min_days",
        config_value="90",
        description="Minimum days before Nashik FTE incentive is payable",
    ))

    # Nashik FTE Leadership (same amounts as SN)
    for role, amt in sn_fte_fixed:
        rows.append(_row(
            division="nashik",
            rule_category="FTE_LEADERSHIP",
            role=role,
            amount=Decimal(amt),
            description=f"Nashik FTE one-time for {role} after 90 days",
        ))

    # =========================================================================
    # AMPCUS TECH CLIENT DIVISION
    # =========================================================================

    # ── ATC Global Config ─────────────────────────────────────────────────────
    rows.append(_row(
        division="ampcusTechClient",
        rule_category="GLOBAL_CONFIG",
        rule_key="requires_first_full_month_payment",
        config_value="true",
        description="First full calendar month payment required before markup slab incentive is paid",
    ))
    rows.append(_row(
        division="ampcusTechClient",
        rule_category="GLOBAL_CONFIG",
        rule_key="max_roles_per_person",
        config_value="2",
        description="Maximum eligible roles per person",
    ))

    # ── ATC Markup Slabs ─────────────────────────────────────────────────────
    # SLABS from ampcus_client.py — per-role amounts stored as JSON in config_value
    import json
    atc_roles = [
        "Recruiter", "Team Lead", "Manager", "Senior Manager",
        "CRM", "Associate Director", "Center Head", "AVP", "Director",
    ]
    atc_slabs = [
        ("0", "5.00", {r: 0 for r in atc_roles}),
        ("5.01", "10", {"Recruiter": 2000, "Team Lead": 250, "Manager": 500, "Senior Manager": 500, "CRM": 750, "Associate Director": 500, "Center Head": 500, "AVP": 500, "Director": 500}),
        ("10.01", "15", {"Recruiter": 3000, "Team Lead": 250, "Manager": 500, "Senior Manager": 500, "CRM": 750, "Associate Director": 1000, "Center Head": 1000, "AVP": 1000, "Director": 1000}),
        ("15.01", "20", {"Recruiter": 5000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1000, "Associate Director": 1500, "Center Head": 1500, "AVP": 1500, "Director": 1500}),
        ("20.01", "25", {"Recruiter": 6000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 2000, "Center Head": 2000, "AVP": 2000, "Director": 2000}),
        ("25.01", "30", {"Recruiter": 7000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 2500, "Center Head": 2500, "AVP": 2500, "Director": 2500}),
        ("30.01", "35", {"Recruiter": 8000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 3000, "Center Head": 3000, "AVP": 3000, "Director": 3000}),
        ("35.01", "40", {"Recruiter": 9000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 3500, "Center Head": 3500, "AVP": 3500, "Director": 3500}),
        ("40.01", "100", {"Recruiter": 10000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 4000, "Center Head": 4000, "AVP": 4000, "Director": 4000}),
    ]
    for mk_lo, mk_hi, role_amounts in atc_slabs:
        rows.append(_row(
            division="ampcusTechClient",
            rule_category="MARKUP_SLAB",
            markup_min=Decimal(mk_lo),
            markup_max=Decimal(mk_hi),
            config_value=json.dumps(role_amounts),
            description=f"ATC markup slab {mk_lo}%–{mk_hi}%: per-role INR amounts",
        ))

    # =========================================================================
    # AMPCUS TECH INHOUSE DIVISION
    # =========================================================================

    # ── Inhouse Global Config ─────────────────────────────────────────────────
    inhouse_config = [
        ("min_days", "90", "Minimum days after start date before inhouse incentive is payable"),
        ("min_start_date", "2025-07-01", "Minimum start date for inhouse policy eligibility"),
        ("max_roles_per_person", "2", "Maximum eligible roles per person"),
    ]
    for key, val, desc in inhouse_config:
        rows.append(_row(
            division="ampcusTechInhouse",
            rule_category="GLOBAL_CONFIG",
            rule_key=key,
            config_value=val,
            description=desc,
        ))

    # ── Inhouse Role Amounts ──────────────────────────────────────────────────
    # Recruiter amount depends on job_level (below_manager / above_manager)
    inhouse_amounts = [
        ("Recruiter", "inhouse_recruiter_below_manager", 3000,
         "Recruiter incentive for job level 'below manager'"),
        ("Recruiter", "inhouse_recruiter_above_manager", 5000,
         "Recruiter incentive for job level 'above manager'"),
        ("Manager", "inhouse_manager", 500,
         "Flat Manager incentive after 90 days"),
        ("Center Head", "inhouse_center_head", 1000,
         "Flat Center Head incentive after 90 days"),
    ]
    for role, key, amt, desc in inhouse_amounts:
        rows.append(_row(
            division="ampcusTechInhouse",
            rule_category="INHOUSE_AMOUNTS",
            role=role,
            rule_key=key,
            amount=Decimal(amt),
            description=desc,
        ))

    return rows


def seed_rules_for_new_division(
    db: Session, division_code: str, calculation_engine: str = "MARGIN_SLABS_PRO_RATA"
) -> int:
    """Seed baseline master rules for a newly created division based on calculation methodology."""
    import json
    from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster

    rows: List[Dict[str, Any]] = []
    engine_type = (calculation_engine or "MARGIN_SLABS_PRO_RATA").strip().upper()

    if engine_type == "MARGIN_HOURS_MATRIX":
        # 1. Global config
        sn_cfg = [
            ("standard_hours", "160", "Standard hours for recruiter matrix bucket"),
            ("fte_finder_fee_threshold", "4500", "Finder fee threshold separating below/above FTE slab (INR)"),
            ("fte_min_days", "90", "Minimum days before FTE incentive is payable"),
            ("max_roles_per_person", "2", "Maximum eligible roles per person"),
        ]
        for key, val, desc in sn_cfg:
            rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key=key, config_value=val, description=desc))

        # 2. 8x5 bands
        sn_bands = [
            ("1.00", "2.00", (0, 0, 0, 500, 500)),
            ("2.01", "4.00", (0, 0, 500, 1000, 1000)),
            ("4.01", "6.00", (0, 500, 1000, 1500, 1500)),
            ("6.01", "8.00", (500, 1000, 1500, 2000, 2000)),
            ("8.01", "10.00", (500, 1000, 2000, 2500, 2500)),
            ("10.01", "15.00", (1000, 1500, 2500, 3500, 3500)),
            ("15.01", "20.00", (1000, 2000, 3000, 4000, 4000)),
            ("20.01", "9999.00", (1000, 2000, 3000, 4000, 4500)),
        ]
        hour_buckets = [
            (Decimal("0"), Decimal("40"), "0–40h"),
            (Decimal("41"), Decimal("80"), "41–80h"),
            (Decimal("81"), Decimal("120"), "81–120h"),
            (Decimal("121"), Decimal("160"), "121–160h"),
            (Decimal("161"), None, "161+h"),
        ]
        for lo, hi, amts in sn_bands:
            for idx, (h_lo, h_hi, h_label) in enumerate(hour_buckets):
                rows.append(_row(
                    division=division_code,
                    rule_category="RECRUITER_SLAB",
                    role="Recruiter",
                    margin_min=Decimal(lo),
                    margin_max=Decimal(hi),
                    hours_min=h_lo,
                    hours_max=h_hi,
                    amount=Decimal(amts[idx]),
                    description=f"{division_code} matrix: ${lo}–${hi}/hr, {h_label}",
                ))

        # 3. Leadership fixed
        sn_fixed = [
            ("Team Lead", 500),
            ("Manager", 1000),
            ("Senior Manager", 1000),
            ("CRM", 1000),
            ("Associate Director", 1750),
            ("Director", 1750),
            ("Center Head", 1500),
            ("AVP", 2300),
        ]
        for role, amt in sn_fixed:
            rows.append(_row(
                division=division_code,
                rule_category="LEADERSHIP_ONE_TIME",
                role=role,
                amount=Decimal(amt),
                description=f"{division_code} fixed rate for {role} on 160h cumulative",
            ))

        # 4. FTE Recruiter slabs
        fte_slabs = [
            (False, (15000, 20000, 25000)),
            (True, (20000, 25000, 30000)),
        ]
        placement_buckets = [
            (1, 1, "1st placement"),
            (2, 2, "2nd placement"),
            (3, None, "3rd+ placement"),
        ]
        for above, amts in fte_slabs:
            for idx, (cnt_min, cnt_max, p_label) in enumerate(placement_buckets):
                rows.append(_row(
                    division=division_code,
                    rule_category="FTE_RECRUITER_SLAB",
                    role="Recruiter",
                    finder_fee_above=above,
                    placement_count_min=cnt_min,
                    placement_count_max=cnt_max,
                    amount=Decimal(amts[idx]),
                    description=f"FTE recruiter: {'≥$4,500' if above else '<$4,500'}, {p_label}",
                ))
        for role, amt in [("Team Lead", 500), ("Manager", 1000), ("Associate Director", 1500)]:
            rows.append(_row(division=division_code, rule_category="FTE_LEADERSHIP", role=role, amount=Decimal(amt), description=f"FTE leadership for {role}"))

    elif engine_type == "CLIENT_MARKUP_PERCENT":
        rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key="requires_first_full_month_payment", config_value="true", description="First full month client payment required"))
        rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key="max_roles_per_person", config_value="2", description="Maximum eligible roles per person"))
        atc_roles = ["Recruiter", "Team Lead", "Manager", "Senior Manager", "CRM", "Associate Director", "Center Head", "AVP", "Director"]
        atc_slabs = [
            ("0", "5.00", {r: 0 for r in atc_roles}),
            ("5.01", "10", {"Recruiter": 2000, "Team Lead": 250, "Manager": 500, "Senior Manager": 500, "CRM": 750, "Associate Director": 500, "Center Head": 500, "AVP": 500, "Director": 500}),
            ("10.01", "15", {"Recruiter": 3000, "Team Lead": 250, "Manager": 500, "Senior Manager": 500, "CRM": 750, "Associate Director": 1000, "Center Head": 1000, "AVP": 1000, "Director": 1000}),
            ("15.01", "20", {"Recruiter": 5000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1000, "Associate Director": 1500, "Center Head": 1500, "AVP": 1500, "Director": 1500}),
            ("20.01", "25", {"Recruiter": 6000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 2000, "Center Head": 2000, "AVP": 2000, "Director": 2000}),
            ("25.01", "30", {"Recruiter": 7000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 2500, "Center Head": 2500, "AVP": 2500, "Director": 2500}),
            ("30.01", "35", {"Recruiter": 8000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 3000, "Center Head": 3000, "AVP": 3000, "Director": 3000}),
            ("35.01", "40", {"Recruiter": 9000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 3500, "Center Head": 3500, "AVP": 3500, "Director": 3500}),
            ("40.01", "100", {"Recruiter": 10000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 4000, "Center Head": 4000, "AVP": 4000, "Director": 4000}),
        ]
        for mk_lo, mk_hi, role_amounts in atc_slabs:
            rows.append(_row(division=division_code, rule_category="MARKUP_SLAB", markup_min=Decimal(mk_lo), markup_max=Decimal(mk_hi), config_value=json.dumps(role_amounts), description=f"{division_code} markup slab {mk_lo}%–{mk_hi}%"))

    elif engine_type == "INHOUSE_FLAT_RATES":
        rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key="min_days", config_value="90", description="Minimum days after start date before inhouse incentive is payable"))
        rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key="min_start_date", config_value="2025-07-01", description="Minimum start date for policy eligibility"))
        rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key="max_roles_per_person", config_value="2", description="Maximum eligible roles per person"))
        inhouse_amounts = [
            ("Recruiter", "inhouse_recruiter_below_manager", 3000, "Recruiter incentive for job level 'below manager'"),
            ("Recruiter", "inhouse_recruiter_above_manager", 5000, "Recruiter incentive for job level 'above manager'"),
            ("Manager", "inhouse_manager", 500, "Flat Manager incentive after 90 days"),
            ("Center Head", "inhouse_center_head", 1000, "Flat Center Head incentive after 90 days"),
        ]
        for role, key, amt, desc in inhouse_amounts:
            rows.append(_row(division=division_code, rule_category="INHOUSE_AMOUNTS", role=role, rule_key=key, amount=Decimal(amt), description=desc))

    else:
        # Default MARGIN_SLABS_PRO_RATA (Nashik style)
        nashik_config = [
            ("standard_hours", "160", "Standard hours per month for pro-rata calculation"),
            ("low_margin_threshold", "1.00", "Margin/hour threshold below which low-margin special rule applies (USD)"),
            ("low_margin_one_time_amount", "2000", "One-time INR incentive for recruiter when margin < $1/hr"),
            ("team_lead_base", "250", "Base INR per placement per 160h for Team Lead (pro-rated)"),
            ("project_end_recruiter_amount", "2000", "Flat INR for recruiter when project ends before 160h"),
            ("max_roles_per_person", "2", "Maximum eligible roles any single person can hold in a placement"),
            ("leadership_hours_requirement", "160", "Cumulative hours required before one-time leadership incentive triggers"),
        ]
        for key, val, desc in nashik_config:
            rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key=key, config_value=val, description=desc))
        nashik_slabs = [
            ("1.00", "2.00", 500),
            ("2.01", "4.00", 1000),
            ("4.01", "6.00", 1500),
            ("6.01", "8.00", 2000),
            ("8.01", "10.00", 2500),
            ("10.01", "15.00", 3500),
            ("15.01", "20.00", 4000),
            ("20.01", "30.00", 4500),
            ("30.01", "40.00", 7000),
            ("40.01", "50.00", 10000),
        ]
        for lo, hi, amt in nashik_slabs:
            rows.append(_row(division=division_code, rule_category="RECRUITER_SLAB", role="Recruiter", margin_min=Decimal(lo), margin_max=Decimal(hi), amount=Decimal(amt), description=f"{division_code} recruiter incentive for margin ${lo}–${hi}/hr"))
        nashik_leadership = [
            ("CRM", 1000),
            ("Manager", 1500),
            ("Senior Manager", 1500),
            ("Associate Director", 1750),
            ("Director", 1750),
            ("Center Head", 1500),
            ("AVP", 2300),
        ]
        for role, amt in nashik_leadership:
            rows.append(_row(division=division_code, rule_category="LEADERSHIP_ONE_TIME", role=role, amount=Decimal(amt), description=f"{division_code} one-time incentive for {role} on 160h+ completion"))
        rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key="fte_finder_fee_threshold", config_value="4500", description="Finder fee threshold separating below/above FTE slab (INR)"))
        rows.append(_row(division=division_code, rule_category="GLOBAL_CONFIG", rule_key="fte_min_days", config_value="90", description="Minimum days before FTE incentive is payable"))
        for above, amts in [(False, (15000, 20000, 25000)), (True, (20000, 25000, 30000))]:
            for idx, (cnt_min, cnt_max, p_label) in enumerate([(1, 1, "1st placement"), (2, 2, "2nd placement"), (3, None, "3rd+ placement")]):
                rows.append(_row(division=division_code, rule_category="FTE_RECRUITER_SLAB", role="Recruiter", finder_fee_above=above, placement_count_min=cnt_min, placement_count_max=cnt_max, amount=Decimal(amts[idx]), description=f"{division_code} FTE recruiter: {'≥$4,500' if above else '<$4,500'}, {p_label}"))
        for role, amt in [("Team Lead", 500), ("Manager", 1000), ("Associate Director", 1500)]:
            rows.append(_row(division=division_code, rule_category="FTE_LEADERSHIP", role=role, amount=Decimal(amt), description=f"{division_code} FTE leadership for {role}"))

    for data in rows:
        db.add(IncentiveRuleMaster(**data))
    db.flush()
    return len(rows)

