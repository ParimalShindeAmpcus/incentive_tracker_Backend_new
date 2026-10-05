"""Rule loader: reads incentive_rule_master from DB and builds typed config dataclasses.

Each calculator engine receives one of these dataclasses instead of hardcoded constants.
If the DB table is empty or has no active rules for a division, the loader falls back
to the existing hardcoded constants so behaviour is always defined.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from prism.repositories.incentive_rules.incentive_rules_repository import (
    load_active_rules_for_division,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed config dataclasses consumed by calculator engines
# ---------------------------------------------------------------------------


@dataclass
class NashikRuleConfig:
    """Configuration for the Nashik Division calculator."""

    standard_hours: Decimal = Decimal("160")
    low_margin_threshold: Decimal = Decimal("1.00")
    low_margin_one_time: Decimal = Decimal("2000")
    team_lead_base: Decimal = Decimal("250")
    project_end_recruiter: Decimal = Decimal("2000")
    max_roles_per_person: int = 2
    leadership_hours_requirement: Decimal = Decimal("160")
    fte_finder_fee_threshold: Decimal = Decimal("4500")
    fte_min_days: int = 90

    # (margin_min, margin_max, amount)
    recruiter_slabs: List[Tuple[Decimal, Decimal, Decimal]] = field(default_factory=list)
    # role -> amount
    leadership_one_time: Dict[str, Decimal] = field(default_factory=dict)
    # FTE: {finder_fee_above: (count1_amt, count2_amt, count3plus_amt)}
    fte_recruiter_slabs: Dict[bool, Tuple[Decimal, Decimal, Decimal]] = field(default_factory=dict)
    # FTE leadership: role -> amount
    fte_leadership: Dict[str, Decimal] = field(default_factory=dict)


@dataclass
class SNRuleConfig:
    """Configuration for the Sambhaji Nagar Division calculator."""

    standard_hours: Decimal = Decimal("160")
    fte_finder_fee_threshold: Decimal = Decimal("4500")
    fte_min_days: int = 90
    max_roles_per_person: int = 2

    # Recruiter Special Incentive Plan (Multiple Placements)
    special_incentive_enabled: bool = True
    special_min_placements: int = 2
    special_min_hours: Decimal = Decimal("160")
    special_evaluation_hours: Decimal = Decimal("161")

    # (margin_min, margin_max, (h0_40, h41_80, h81_120, h121_160, h161plus))
    bands: List[Tuple[Decimal, Decimal, Tuple[Decimal, ...]]] = field(default_factory=list)
    # W2/C2C leadership: role -> amount
    fixed: Dict[str, Decimal] = field(default_factory=dict)
    # FTE leadership: role -> amount
    fte_fixed: Dict[str, Decimal] = field(default_factory=dict)
    # {finder_fee_above: (cnt1_amt, cnt2_amt, cnt3plus_amt)}
    fte_recruiter_slabs: Dict[bool, Tuple[Decimal, Decimal, Decimal]] = field(default_factory=dict)


@dataclass
class ATCRuleConfig:
    """Configuration for the Ampcus Tech Client calculator."""

    max_roles_per_person: int = 2
    requires_first_full_month_payment: bool = True
    # (markup_min, markup_max, {role: amount})
    slabs: List[Tuple[Decimal, Decimal, Dict[str, int]]] = field(default_factory=list)

    # ATC FTE fields
    fte_finder_fee_threshold: Decimal = Decimal("4500")
    # {finder_fee_above: (cnt1_amt, cnt2_amt, cnt3plus_amt)}
    fte_recruiter_slabs: Dict[bool, Tuple[Decimal, Decimal, Decimal]] = field(default_factory=dict)
    # leadership role -> fixed amount per FTE placement
    fte_fixed: Dict[str, int] = field(default_factory=dict)


@dataclass
class InhouseRuleConfig:
    """Configuration for the Ampcus Tech Inhouse calculator."""

    min_days: int = 90
    min_start_date: date = date(2025, 7, 1)
    max_roles_per_person: int = 2
    recruiter_below_manager: int = 3000
    recruiter_above_manager: int = 5000
    manager_amount: int = 500
    center_head_amount: int = 1000


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_nashik_config(
    db: Session, effective_on: Optional[date] = None, division: str = "nashik"
) -> NashikRuleConfig:
    """Build NashikRuleConfig from DB; falls back to hardcoded defaults."""
    rules = load_active_rules_for_division(db, division, effective_on=effective_on)
    if not rules:
        logger.debug("No active %s rules in DB; using hardcoded defaults.", division)
        return _nashik_hardcoded_defaults()

    cfg = NashikRuleConfig()
    _apply_global_config_nashik(cfg, rules)
    _apply_nashik_recruiter_slabs(cfg, rules)
    _apply_nashik_leadership(cfg, rules)
    _apply_fte_recruiter_slabs(cfg, division, rules)
    _apply_fte_leadership(cfg, rules)

    # Validate — fall back to hardcoded if slabs are empty (shouldn't happen)
    if not cfg.recruiter_slabs:
        logger.warning("%s recruiter slabs empty in DB; using hardcoded defaults.", division)
        return _nashik_hardcoded_defaults()

    return cfg


def load_sn_config(
    db: Session, effective_on: Optional[date] = None, division: str = "sambhajiNagar"
) -> SNRuleConfig:
    """Build SNRuleConfig from DB; falls back to hardcoded defaults."""
    rules = load_active_rules_for_division(db, division, effective_on=effective_on)
    if not rules:
        logger.debug("No active %s rules in DB; using hardcoded defaults.", division)
        return _sn_hardcoded_defaults()

    cfg = SNRuleConfig()
    _apply_global_config_sn(cfg, rules)
    _apply_sn_bands(cfg, rules)
    _apply_sn_fixed(cfg, rules)
    _apply_sn_fte_fixed(cfg, rules)
    _apply_fte_recruiter_slabs_sn(cfg, rules)

    if not cfg.bands:
        logger.warning("%s bands empty in DB; using hardcoded defaults.", division)
        return _sn_hardcoded_defaults()

    return cfg


def load_atc_config(
    db: Session, effective_on: Optional[date] = None, division: str = "ampcusTechClient"
) -> ATCRuleConfig:
    """Build ATCRuleConfig from DB; falls back to hardcoded defaults."""
    rules = load_active_rules_for_division(db, division, effective_on=effective_on)
    if not rules:
        logger.debug("No active %s rules in DB; using hardcoded defaults.", division)
        return _atc_hardcoded_defaults()

    cfg = ATCRuleConfig()
    fte_slab_map: Dict[bool, Dict[int, Decimal]] = {False: {}, True: {}}

    for r in rules:
        if r.rule_category == "GLOBAL_CONFIG":
            if r.rule_key == "requires_first_full_month_payment":
                cfg.requires_first_full_month_payment = (r.config_value or "true").lower() == "true"
            elif r.rule_key == "max_roles_per_person":
                cfg.max_roles_per_person = int(r.config_value or "2")
            elif r.rule_key == "fte_finder_fee_threshold":
                cfg.fte_finder_fee_threshold = Decimal(r.config_value or "4500")
        elif r.rule_category == "MARKUP_SLAB":
            try:
                role_amounts: Dict[str, int] = json.loads(r.config_value or "{}")
            except Exception:
                role_amounts = {}
            cfg.slabs.append((
                Decimal(str(r.markup_min or "0")),
                Decimal(str(r.markup_max or "0")),
                role_amounts,
            ))
        elif r.rule_category == "FTE_RECRUITER_SLAB" and r.finder_fee_above is not None:
            cnt_min = r.placement_count_min or 1
            fte_slab_map[r.finder_fee_above][cnt_min] = Decimal(str(r.amount or "0"))
        elif r.rule_category == "FTE_LEADERSHIP" and r.role:
            cfg.fte_fixed[r.role] = int(r.amount or 0)

    # Reconstruct fte_recruiter_slabs tuples from the per-count map
    for above, by_count in fte_slab_map.items():
        if len(by_count) >= 3:
            cfg.fte_recruiter_slabs[above] = (
                by_count.get(1, Decimal("0")),
                by_count.get(2, Decimal("0")),
                by_count.get(3, Decimal("0")),
            )

    cfg.slabs.sort(key=lambda s: s[0])
    if not cfg.slabs:
        return _atc_hardcoded_defaults()

    return cfg


def load_inhouse_config(
    db: Session, effective_on: Optional[date] = None, division: str = "ampcusTechInhouse"
) -> InhouseRuleConfig:
    """Build InhouseRuleConfig from DB; falls back to hardcoded defaults."""
    rules = load_active_rules_for_division(db, division, effective_on=effective_on)
    if not rules:
        logger.debug("No active %s rules in DB; using hardcoded defaults.", division)
        return _inhouse_hardcoded_defaults()

    cfg = InhouseRuleConfig()
    for r in rules:
        if r.rule_category == "GLOBAL_CONFIG":
            if r.rule_key == "min_days":

                cfg.min_days = int(r.config_value or "90")
            elif r.rule_key == "min_start_date":
                try:
                    cfg.min_start_date = date.fromisoformat(r.config_value or "2025-07-01")
                except ValueError:
                    pass
            elif r.rule_key == "max_roles_per_person":
                cfg.max_roles_per_person = int(r.config_value or "2")
        elif r.rule_category == "INHOUSE_AMOUNTS":
            amt = int(r.amount or 0)
            if r.rule_key == "inhouse_recruiter_below_manager":
                cfg.recruiter_below_manager = amt
            elif r.rule_key == "inhouse_recruiter_above_manager":
                cfg.recruiter_above_manager = amt
            elif r.rule_key == "inhouse_manager":
                cfg.manager_amount = amt
            elif r.rule_key == "inhouse_center_head":
                cfg.center_head_amount = amt

    return cfg


# ---------------------------------------------------------------------------
# Internal helpers — apply rules from DB rows to config objects
# ---------------------------------------------------------------------------


def _apply_global_config_nashik(cfg: NashikRuleConfig, rules: list) -> None:
    for r in rules:
        if r.rule_category != "GLOBAL_CONFIG":
            continue
        v = r.config_value or ""
        if r.rule_key == "standard_hours":
            cfg.standard_hours = Decimal(v)
        elif r.rule_key == "low_margin_threshold":
            cfg.low_margin_threshold = Decimal(v)
        elif r.rule_key == "low_margin_one_time_amount":
            cfg.low_margin_one_time = Decimal(v)
        elif r.rule_key == "team_lead_base":
            cfg.team_lead_base = Decimal(v)
        elif r.rule_key == "project_end_recruiter_amount":
            cfg.project_end_recruiter = Decimal(v)
        elif r.rule_key == "max_roles_per_person":
            cfg.max_roles_per_person = int(v)
        elif r.rule_key == "leadership_hours_requirement":
            cfg.leadership_hours_requirement = Decimal(v)
        elif r.rule_key == "fte_finder_fee_threshold":
            cfg.fte_finder_fee_threshold = Decimal(v)
        elif r.rule_key == "fte_min_days":
            cfg.fte_min_days = int(v)


def _apply_nashik_recruiter_slabs(cfg: NashikRuleConfig, rules: list) -> None:
    slabs = []
    for r in rules:
        if r.rule_category == "RECRUITER_SLAB" and r.role == "Recruiter":
            slabs.append((
                Decimal(str(r.margin_min)),
                Decimal(str(r.margin_max)),
                Decimal(str(r.amount)),
            ))
    cfg.recruiter_slabs = sorted(slabs, key=lambda s: s[0])


def _apply_nashik_leadership(cfg: NashikRuleConfig, rules: list) -> None:
    for r in rules:
        if r.rule_category == "LEADERSHIP_ONE_TIME" and r.role:
            cfg.leadership_one_time[r.role] = Decimal(str(r.amount))


def _apply_fte_recruiter_slabs(cfg: NashikRuleConfig, division: str, rules: list) -> None:
    slabs: Dict[bool, Dict[int, Decimal]] = {False: {}, True: {}}
    for r in rules:
        if r.rule_category == "FTE_RECRUITER_SLAB" and r.finder_fee_above is not None:
            cnt_min = r.placement_count_min or 1
            slabs[r.finder_fee_above][cnt_min] = Decimal(str(r.amount))
    result: Dict[bool, Tuple[Decimal, Decimal, Decimal]] = {}
    for above, by_count in slabs.items():
        if len(by_count) >= 3:
            result[above] = (by_count[1], by_count[2], by_count[3])
    cfg.fte_recruiter_slabs = result


def _apply_fte_leadership(cfg: NashikRuleConfig, rules: list) -> None:
    for r in rules:
        if r.rule_category == "FTE_LEADERSHIP" and r.role:
            cfg.fte_leadership[r.role] = Decimal(str(r.amount))


def _apply_global_config_sn(cfg: SNRuleConfig, rules: list) -> None:
    for r in rules:
        if r.rule_category != "GLOBAL_CONFIG":
            continue
        v = (r.config_value or "").strip()
        if r.rule_key == "standard_hours":
            cfg.standard_hours = Decimal(v)
        elif r.rule_key == "fte_finder_fee_threshold":
            cfg.fte_finder_fee_threshold = Decimal(v)
        elif r.rule_key == "fte_min_days":
            cfg.fte_min_days = int(v)
        elif r.rule_key == "max_roles_per_person":
            cfg.max_roles_per_person = int(v)
        elif r.rule_key == "special_incentive_enabled":
            cfg.special_incentive_enabled = v.lower() in {"true", "1", "yes"}
        elif r.rule_key == "special_min_placements":
            try:
                cfg.special_min_placements = int(v)
            except (ValueError, TypeError):
                pass
        elif r.rule_key == "special_min_hours":
            try:
                cfg.special_min_hours = Decimal(v)
            except Exception:
                pass
        elif r.rule_key == "special_evaluation_hours":
            try:
                cfg.special_evaluation_hours = Decimal(v)
            except Exception:
                pass


def _apply_sn_bands(cfg: SNRuleConfig, rules: list) -> None:
    """Reconstruct the 8×5 margin×hours matrix."""
    from collections import defaultdict
    margin_map: Dict[Tuple[Decimal, Decimal], Dict[Decimal, Decimal]] = defaultdict(dict)
    for r in rules:
        if r.rule_category == "RECRUITER_SLAB" and r.role == "Recruiter":
            key = (Decimal(str(r.margin_min)), Decimal(str(r.margin_max)))
            h_min = Decimal(str(r.hours_min or "0"))
            margin_map[key][h_min] = Decimal(str(r.amount))

    bands = []
    for (m_lo, m_hi), hours_amounts in sorted(margin_map.items()):
        sorted_amounts = [v for _, v in sorted(hours_amounts.items())]
        if len(sorted_amounts) == 5:
            bands.append((m_lo, m_hi, tuple(sorted_amounts)))
    cfg.bands = bands


def _apply_sn_fixed(cfg: SNRuleConfig, rules: list) -> None:
    for r in rules:
        if r.rule_category == "LEADERSHIP_ONE_TIME" and r.role:
            cfg.fixed[r.role] = Decimal(str(r.amount))


def _apply_sn_fte_fixed(cfg: SNRuleConfig, rules: list) -> None:
    for r in rules:
        if r.rule_category == "FTE_LEADERSHIP" and r.role:
            cfg.fte_fixed[r.role] = Decimal(str(r.amount))


def _apply_fte_recruiter_slabs_sn(cfg: SNRuleConfig, rules: list) -> None:
    slabs: Dict[bool, Dict[int, Decimal]] = {False: {}, True: {}}
    for r in rules:
        if r.rule_category == "FTE_RECRUITER_SLAB" and r.finder_fee_above is not None:
            cnt_min = r.placement_count_min or 1
            slabs[r.finder_fee_above][cnt_min] = Decimal(str(r.amount))
    result: Dict[bool, Tuple[Decimal, Decimal, Decimal]] = {}
    for above, by_count in slabs.items():
        if len(by_count) >= 3:
            result[above] = (by_count[1], by_count[2], by_count[3])
    cfg.fte_recruiter_slabs = result


# ---------------------------------------------------------------------------
# Hardcoded defaults (exact copies of current constants — fallback only)
# ---------------------------------------------------------------------------


def _nashik_hardcoded_defaults() -> NashikRuleConfig:
    cfg = NashikRuleConfig()
    cfg.recruiter_slabs = [
        (Decimal("1.00"), Decimal("2.00"), Decimal("500")),
        (Decimal("2.01"), Decimal("4.00"), Decimal("1000")),
        (Decimal("4.01"), Decimal("6.00"), Decimal("1500")),
        (Decimal("6.01"), Decimal("8.00"), Decimal("2000")),
        (Decimal("8.01"), Decimal("10.00"), Decimal("2500")),
        (Decimal("10.01"), Decimal("15.00"), Decimal("3500")),
        (Decimal("15.01"), Decimal("20.00"), Decimal("4000")),
        (Decimal("20.01"), Decimal("30.00"), Decimal("4500")),
        (Decimal("30.01"), Decimal("40.00"), Decimal("7000")),
        (Decimal("40.01"), Decimal("50.00"), Decimal("10000")),
    ]
    cfg.leadership_one_time = {
        "CRM": Decimal("1000"),
        "Manager": Decimal("1500"),
        "Senior Manager": Decimal("1500"),
        "Associate Director": Decimal("1750"),
        "Director": Decimal("1750"),
        "Center Head": Decimal("1500"),
        "AVP": Decimal("2300"),
    }
    cfg.fte_recruiter_slabs = {
        False: (Decimal("15000"), Decimal("18000"), Decimal("20000")),
        True: (Decimal("20000"), Decimal("25000"), Decimal("30000")),
    }
    cfg.fte_leadership = {
        "Team Lead": Decimal("1000"), "Manager": Decimal("1500"),
        "CRM": Decimal("1500"), "Associate Director": Decimal("4000"),
        "Center Head": Decimal("4000"), "AVP": Decimal("4000"),
        "Director": Decimal("1500"), "Senior Manager": Decimal("1500"),
    }
    return cfg


def _sn_hardcoded_defaults() -> SNRuleConfig:
    cfg = SNRuleConfig()
    cfg.bands = [
        (Decimal("1.00"), Decimal("3.00"), (Decimal("500"), Decimal("1000"), Decimal("2000"), Decimal("3000"), Decimal("4000"))),
        (Decimal("3.01"), Decimal("5.00"), (Decimal("1000"), Decimal("2000"), Decimal("3000"), Decimal("4000"), Decimal("5000"))),
        (Decimal("5.01"), Decimal("7.00"), (Decimal("2000"), Decimal("3000"), Decimal("4000"), Decimal("5000"), Decimal("7000"))),
        (Decimal("7.01"), Decimal("10.00"), (Decimal("3000"), Decimal("4000"), Decimal("5000"), Decimal("6000"), Decimal("8500"))),
        (Decimal("10.01"), Decimal("15.00"), (Decimal("4000"), Decimal("5000"), Decimal("6000"), Decimal("7000"), Decimal("10000"))),
        (Decimal("15.01"), Decimal("20.00"), (Decimal("5000"), Decimal("6000"), Decimal("7000"), Decimal("8000"), Decimal("15000"))),
        (Decimal("20.01"), Decimal("30.00"), (Decimal("6000"), Decimal("7000"), Decimal("8000"), Decimal("10000"), Decimal("20000"))),
        (Decimal("30.01"), Decimal("50.00"), (Decimal("7000"), Decimal("8000"), Decimal("9000"), Decimal("12000"), Decimal("25000"))),
    ]
    cfg.fixed = {
        "Team Lead": Decimal("500"), "Manager": Decimal("1000"),
        "Senior Manager": Decimal("1500"), "CRM": Decimal("1000"),
        "Associate Director": Decimal("1750"), "Center Head": Decimal("1750"),
        "AVP": Decimal("1750"), "Director": Decimal("1000"),
    }
    cfg.fte_fixed = {
        "Team Lead": Decimal("1000"), "Manager": Decimal("1500"),
        "CRM": Decimal("1500"), "Associate Director": Decimal("4000"),
        "Center Head": Decimal("4000"), "AVP": Decimal("4000"),
        "Director": Decimal("1500"), "Senior Manager": Decimal("1500"),
    }
    cfg.fte_recruiter_slabs = {
        False: (Decimal("15000"), Decimal("18000"), Decimal("20000")),
        True: (Decimal("20000"), Decimal("25000"), Decimal("30000")),
    }
    return cfg


def _atc_hardcoded_defaults() -> ATCRuleConfig:
    import json as _json
    cfg = ATCRuleConfig()
    roles = ["Recruiter", "Team Lead", "Manager", "Senior Manager",
             "CRM", "Associate Director", "Center Head", "AVP", "Director"]
    cfg.slabs = [
        (Decimal("0"), Decimal("5.00"), {r: 0 for r in roles}),
        (Decimal("5.01"), Decimal("10"), {"Recruiter": 2000, "Team Lead": 250, "Manager": 500, "Senior Manager": 500, "CRM": 750, "Associate Director": 500, "Center Head": 500, "AVP": 500, "Director": 500}),
        (Decimal("10.01"), Decimal("15"), {"Recruiter": 3000, "Team Lead": 250, "Manager": 500, "Senior Manager": 500, "CRM": 750, "Associate Director": 1000, "Center Head": 1000, "AVP": 1000, "Director": 1000}),
        (Decimal("15.01"), Decimal("20"), {"Recruiter": 5000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1000, "Associate Director": 1500, "Center Head": 1500, "AVP": 1500, "Director": 1500}),
        (Decimal("20.01"), Decimal("25"), {"Recruiter": 6000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 2000, "Center Head": 2000, "AVP": 2000, "Director": 2000}),
        (Decimal("25.01"), Decimal("30"), {"Recruiter": 7000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 2500, "Center Head": 2500, "AVP": 2500, "Director": 2500}),
        (Decimal("30.01"), Decimal("35"), {"Recruiter": 8000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 3000, "Center Head": 3000, "AVP": 3000, "Director": 3000}),
        (Decimal("35.01"), Decimal("40"), {"Recruiter": 9000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 3500, "Center Head": 3500, "AVP": 3500, "Director": 3500}),
        (Decimal("40.01"), Decimal("100"), {"Recruiter": 10000, "Team Lead": 500, "Manager": 1000, "Senior Manager": 1000, "CRM": 1500, "Associate Director": 4000, "Center Head": 4000, "AVP": 4000, "Director": 4000}),
    ]
    return cfg


def _inhouse_hardcoded_defaults() -> InhouseRuleConfig:
    return InhouseRuleConfig()
