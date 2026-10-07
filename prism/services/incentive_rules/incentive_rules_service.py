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


def get_rule(db: Session, rule_id: int) -> Optional[IncentiveRuleMasterOut]:
    row = repo.get_rule(db, rule_id)
    if row is None:
        return None
    return IncentiveRuleMasterOut.model_validate(row)


def create_rule(
    db: Session, payload: IncentiveRuleMasterIn, created_by: Optional[int] = None
) -> IncentiveRuleMasterOut:
    data = payload.model_dump(exclude_unset=False)
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
    row = repo.update_rule(db, rule_id, data, updated_by=updated_by)
    if row is None:
        return None
    return IncentiveRuleMasterOut.model_validate(row)


def toggle_active(
    db: Session, rule_id: int, updated_by: Optional[int] = None
) -> Optional[IncentiveRuleMasterOut]:
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

