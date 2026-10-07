"""Incentive Rules Master business-logic service."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from prism.models.incentive_rules.schemas import (
    IncentiveRuleMasterIn,
    IncentiveRuleMasterOut,
    IncentiveRuleMasterUpdate,
    IncentiveRuleBatchUpdateItem,
)
from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster
from prism.repositories.incentive_rules import incentive_rules_repository as repo


def list_rules(
    db: Session,
    *,
    division: Optional[str] = None,
    rule_category: Optional[str] = None,
    is_active: Optional[bool] = None,
    effective_on: Optional[date] = None,
) -> List[IncentiveRuleMasterOut]:
    rows = repo.list_rules(
        db,
        division=division,
        rule_category=rule_category,
        is_active=is_active,
        effective_on=effective_on,
    )
    return [IncentiveRuleMasterOut.model_validate(r) for r in rows]


from fastapi import HTTPException, status

def get_rule(db: Session, rule_id: int) -> Optional[IncentiveRuleMasterOut]:
    row = repo.get_rule(db, rule_id)
    if row is None:
        return None
    return IncentiveRuleMasterOut.model_validate(row)


def check_duplicate_rule(
    db: Session,
    data: Dict[str, Any],
    exclude_rule_id: Optional[int] = None,
) -> None:
    """Validate that this rule does not duplicate an existing active rule in the same division."""
    division = data.get("division")
    rule_category = data.get("rule_category")
    role = (data.get("role") or "").strip()
    rule_key = (data.get("rule_key") or "").strip()

    if not division or not rule_category:
        return

    # 1. In-House amounts: duplicate if same division + INHOUSE_AMOUNTS + same rule_key or same role+tier
    if rule_category == "INHOUSE_AMOUNTS":
        query = db.query(IncentiveRuleMaster).filter(
            IncentiveRuleMaster.division == division,
            IncentiveRuleMaster.rule_category == "INHOUSE_AMOUNTS",
            IncentiveRuleMaster.is_active == True,
        )
        if exclude_rule_id:
            query = query.filter(IncentiveRuleMaster.id != exclude_rule_id)

        existing = query.all()
        for r in existing:
            # Check exact rule_key match
            if rule_key and r.rule_key and r.rule_key.strip().lower() == rule_key.lower():
                tier_str = "Above Manager Level" if "above" in rule_key.lower() else "Below Manager Level"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"An active rule for '{role or r.role}' ({tier_str}) already exists (Rule #{r.id}). Please edit the existing rule instead of creating a duplicate.",
                )
            # Check role name match within same tier
            if role and r.role and r.role.strip().lower() == role.lower():
                is_cur_above = "above" in rule_key.lower()
                is_r_above = "above" in (r.rule_key or "").lower()
                is_cur_below = "below" in rule_key.lower()
                is_r_below = "below" in (r.rule_key or "").lower()
                if (is_cur_above and is_r_above) or (is_cur_below and is_r_below):
                    tier_str = "Above Manager Level" if is_cur_above else "Below Manager Level"
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"An active rule for '{role}' ({tier_str}) already exists (Rule #{r.id}). Please edit the existing rule instead of creating a duplicate.",
                    )

    # 2. Global Config: duplicate if same division + GLOBAL_CONFIG + same rule_key
    elif rule_category == "GLOBAL_CONFIG":
        if rule_key:
            query = db.query(IncentiveRuleMaster).filter(
                IncentiveRuleMaster.division == division,
                IncentiveRuleMaster.rule_category == "GLOBAL_CONFIG",
                IncentiveRuleMaster.rule_key == rule_key,
                IncentiveRuleMaster.is_active == True,
            )
            if exclude_rule_id:
                query = query.filter(IncentiveRuleMaster.id != exclude_rule_id)
            existing_cfg = query.first()
            if existing_cfg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A configuration setting for '{rule_key}' already exists in this division (Rule #{existing_cfg.id}).",
                )

    # 3. Leadership One-Time & FTE Leadership: duplicate if same division + same category + same role
    elif rule_category in ("LEADERSHIP_ONE_TIME", "FTE_LEADERSHIP"):
        if role:
            query = db.query(IncentiveRuleMaster).filter(
                IncentiveRuleMaster.division == division,
                IncentiveRuleMaster.rule_category == rule_category,
                IncentiveRuleMaster.is_active == True,
            )
            if exclude_rule_id:
                query = query.filter(IncentiveRuleMaster.id != exclude_rule_id)
            for r in query.all():
                if r.role and r.role.strip().lower() == role.lower():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"A leadership rule for '{role}' already exists in this division (Rule #{r.id}).",
                    )


def create_rule(
    db: Session, payload: IncentiveRuleMasterIn, created_by: Optional[int] = None
) -> IncentiveRuleMasterOut:
    data = payload.model_dump(exclude_unset=False)
    check_duplicate_rule(db, data)
    row = repo.create_rule(db, data, created_by=created_by)
    return IncentiveRuleMasterOut.model_validate(row)


def update_rule(
    db: Session,
    rule_id: int,
    payload: IncentiveRuleMasterUpdate,
    updated_by: Optional[int] = None,
) -> Optional[IncentiveRuleMasterOut]:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_rule(db, rule_id)
    existing = repo.get_rule(db, rule_id)
    if existing:
        merged = {
            "division": existing.division,
            "rule_category": existing.rule_category,
            "role": existing.role,
            "rule_key": existing.rule_key,
            **data,
        }
        if data.get("is_active") is not False:
            check_duplicate_rule(db, merged, exclude_rule_id=rule_id)
    row = repo.update_rule(db, rule_id, data, updated_by=updated_by)
    if row is None:
        return None
    return IncentiveRuleMasterOut.model_validate(row)


def toggle_active(
    db: Session, rule_id: int, updated_by: Optional[int] = None
) -> Optional[IncentiveRuleMasterOut]:
    row = repo.get_rule(db, rule_id)
    if row is None:
        return None
    if not row.is_active:
        merged = {
            "division": row.division,
            "rule_category": row.rule_category,
            "role": row.role,
            "rule_key": row.rule_key,
        }
        check_duplicate_rule(db, merged, exclude_rule_id=rule_id)
    row = repo.toggle_active(db, rule_id, updated_by=updated_by)
    if row is None:
        return None
    return IncentiveRuleMasterOut.model_validate(row)


def soft_delete(
    db: Session, rule_id: int, updated_by: Optional[int] = None
) -> Optional[IncentiveRuleMasterOut]:
    row = repo.soft_delete(db, rule_id, updated_by=updated_by)
    if row is None:
        return None
    return IncentiveRuleMasterOut.model_validate(row)


def hard_delete(db: Session, rule_id: int) -> bool:
    return repo.hard_delete(db, rule_id)


def batch_create_rules(
    db: Session, payloads: List[IncentiveRuleMasterIn], created_by: Optional[int] = None
) -> List[IncentiveRuleMasterOut]:
    results = []
    for p in payloads:
        data = p.model_dump(exclude_unset=False)
        row = repo.create_rule(db, data, created_by=created_by)
        results.append(row)
    db.commit()
    for r in results:
        db.refresh(r)
    return [IncentiveRuleMasterOut.model_validate(r) for r in results]


def batch_update_rules(
    db: Session, items: List[IncentiveRuleBatchUpdateItem], updated_by: Optional[int] = None
) -> List[IncentiveRuleMasterOut]:
    results = []
    for item in items:
        data = item.data.model_dump(exclude_unset=True)
        if data:
            row = repo.update_rule(db, item.id, data, updated_by=updated_by)
            if row:
                results.append(row)
    db.commit()
    for r in results:
        db.refresh(r)
    return [IncentiveRuleMasterOut.model_validate(r) for r in results]


def batch_delete_rules(
    db: Session, ids: List[int], hard: bool = True, updated_by: Optional[int] = None
) -> int:
    deleted_count = 0
    for rule_id in ids:
        if hard:
            if repo.hard_delete(db, rule_id):
                deleted_count += 1
        else:
            if repo.soft_delete(db, rule_id, updated_by=updated_by):
                deleted_count += 1
    db.commit()
    return deleted_count

