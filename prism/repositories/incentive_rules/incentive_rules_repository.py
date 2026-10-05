"""Incentive Rules Master repository — raw SQL/ORM layer."""

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster

# ---------------------------------------------------------------------------
# Division Aliases for query normalisation and engine compatibility
# ---------------------------------------------------------------------------

DIVISION_ALIASES: Dict[str, str] = {
    "nd": "nashik",
    "nashik": "nashik",
    "nashikdivision": "nashik",
    "sn": "sambhajiNagar",
    "sambhajinagar": "sambhajiNagar",
    "sambhajinagardivision": "sambhajiNagar",
    "atc": "ampcusTechClient",
    "ampcustechclient": "ampcusTechClient",
    "ampcus_client": "ampcusTechClient",
    "ampcusclient": "ampcusTechClient",
    "ampcustechinhouse": "ampcusTechInhouse",
    "ampcus_inhouse": "ampcusTechInhouse",
    "ampcusinhouse": "ampcusTechInhouse",
    "inhouse": "ampcusTechInhouse",
}


def resolve_division_code(division: Optional[str]) -> Optional[str]:
    """Normalize division aliases into standard canonical keys."""
    if not division:
        return division
    cleaned = division.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    return DIVISION_ALIASES.get(cleaned, division.strip())


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


def list_rules(
    db: Session,
    *,
    division: Optional[str] = None,
    rule_category: Optional[str] = None,
    is_active: Optional[bool] = None,
    effective_on: Optional[date] = None,
) -> List[IncentiveRuleMaster]:
    q = db.query(IncentiveRuleMaster)
    if division is not None:
        target_division = resolve_division_code(division) or division
        q = q.filter(
            or_(
                func.lower(IncentiveRuleMaster.division) == target_division.lower(),
                func.lower(IncentiveRuleMaster.division) == division.strip().lower(),
            )
        )
    if rule_category is not None:
        q = q.filter(func.lower(IncentiveRuleMaster.rule_category) == rule_category.strip().lower())
    if is_active is not None:
        q = q.filter(IncentiveRuleMaster.is_active.is_(is_active))
    if effective_on is not None:
        q = q.filter(
            IncentiveRuleMaster.effective_from <= effective_on,
            (IncentiveRuleMaster.effective_to.is_(None))
            | (IncentiveRuleMaster.effective_to >= effective_on),
        )
    return (
        q.order_by(
            IncentiveRuleMaster.division,
            IncentiveRuleMaster.rule_category,
            IncentiveRuleMaster.role,
            IncentiveRuleMaster.margin_min,
            IncentiveRuleMaster.hours_min,
            IncentiveRuleMaster.markup_min,
            IncentiveRuleMaster.placement_count_min,
            IncentiveRuleMaster.id,
        )
        .all()
    )


def get_rule(db: Session, rule_id: int) -> Optional[IncentiveRuleMaster]:
    return (
        db.query(IncentiveRuleMaster)
        .filter(IncentiveRuleMaster.id == rule_id)
        .first()
    )


def create_rule(
    db: Session, data: Dict[str, Any], created_by: Optional[int] = None
) -> IncentiveRuleMaster:
    row = IncentiveRuleMaster(**{k: v for k, v in data.items() if v is not None or k in _NULLABLE_FIELDS})
    if created_by:
        row.created_by = created_by
        row.updated_by = created_by
    db.add(row)
    db.flush()
    db.refresh(row)
    return row


def update_rule(
    db: Session,
    rule_id: int,
    data: Dict[str, Any],
    updated_by: Optional[int] = None,
) -> Optional[IncentiveRuleMaster]:
    row = get_rule(db, rule_id)
    if row is None:
        return None
    for key, val in data.items():
        if val is not None or key in _NULLABLE_FIELDS:
            setattr(row, key, val)
    if updated_by:
        row.updated_by = updated_by
    db.flush()
    db.refresh(row)
    return row


def toggle_active(
    db: Session, rule_id: int, updated_by: Optional[int] = None
) -> Optional[IncentiveRuleMaster]:
    row = get_rule(db, rule_id)
    if row is None:
        return None
    row.is_active = not row.is_active
    if updated_by:
        row.updated_by = updated_by
    db.flush()
    db.refresh(row)
    return row


def soft_delete(
    db: Session, rule_id: int, updated_by: Optional[int] = None
) -> Optional[IncentiveRuleMaster]:
    """Soft-delete: set is_active=False."""
    row = get_rule(db, rule_id)
    if row is None:
        return None
    row.is_active = False
    if updated_by:
        row.updated_by = updated_by
    db.flush()
    db.refresh(row)
    return row


def hard_delete(db: Session, rule_id: int) -> bool:
    """Permanently delete rule from database."""
    row = get_rule(db, rule_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


# ---------------------------------------------------------------------------
# Bulk-load helpers used by the rule_loader
# ---------------------------------------------------------------------------


def load_active_rules_for_division(
    db: Session,
    division: str,
    effective_on: Optional[date] = None,
) -> List[IncentiveRuleMaster]:
    """Return all active rules for a division, optionally date-filtered with alias resolution."""
    rules = list_rules(
        db,
        division=division,
        is_active=True,
        effective_on=effective_on,
    )
    if not rules:
        target = resolve_division_code(division)
        if target and target.lower() != division.strip().lower():
            rules = list_rules(
                db,
                division=target,
                is_active=True,
                effective_on=effective_on,
            )
    return rules


def has_any_rules(db: Session) -> bool:
    """True when the master table is non-empty (used by seed guard)."""
    return db.query(IncentiveRuleMaster).limit(1).count() > 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Fields that should be set even when value is None (they're genuinely nullable)
_NULLABLE_FIELDS = {
    "role",
    "rule_key",
    "margin_min",
    "margin_max",
    "hours_min",
    "hours_max",
    "markup_min",
    "markup_max",
    "placement_count_min",
    "placement_count_max",
    "finder_fee_above",
    "amount",
    "config_value",
    "description",
    "effective_to",
}
