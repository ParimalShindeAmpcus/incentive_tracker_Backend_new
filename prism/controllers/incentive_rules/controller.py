"""Incentive Rules Master HTTP controller — Admin-only CRUD endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from prism.models.incentive_rules.schemas import (
    IncentiveRuleMasterIn,
    IncentiveRuleMasterOut,
    IncentiveRuleMasterUpdate,
    IncentiveRuleBatchUpdateItem,
    IncentiveRuleBatchDeleteIn,
)
from prism.repositories.entities.user import User
from prism.services.common.deps import DbSession, get_current_user, require_roles
from prism.services.incentive_rules import incentive_rules_service as svc

router = APIRouter(dependencies=[Depends(get_current_user)])

AdminUser = Annotated[User, Depends(require_roles("ADMIN"))]


@router.get("/incentive-rules", response_model=List[IncentiveRuleMasterOut])
def list_incentive_rules(
    db: DbSession,
    _user: AdminUser,
    division: Optional[str] = Query(None, description="Filter by division key"),
    rule_category: Optional[str] = Query(None, description="Filter by rule_category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    effective_on: Optional[date] = Query(None, description="Return rules effective on this date (YYYY-MM-DD)"),
) -> List[IncentiveRuleMasterOut]:
    """List incentive rules with optional filters. Admin only."""
    return svc.list_rules(
        db,
        division=division,
        rule_category=rule_category,
        is_active=is_active,
        effective_on=effective_on,
    )


@router.post("/incentive-rules/batch", response_model=List[IncentiveRuleMasterOut], status_code=status.HTTP_201_CREATED)
def batch_create_incentive_rules(
    payloads: List[IncentiveRuleMasterIn],
    db: DbSession,
    user: AdminUser,
) -> List[IncentiveRuleMasterOut]:
    """Batch create multiple incentive rules. Admin only."""
    return svc.batch_create_rules(db, payloads, created_by=user.id)


@router.put("/incentive-rules/batch", response_model=List[IncentiveRuleMasterOut])
def batch_update_incentive_rules(
    items: List[IncentiveRuleBatchUpdateItem],
    db: DbSession,
    user: AdminUser,
) -> List[IncentiveRuleMasterOut]:
    """Batch update multiple incentive rules. Admin only."""
    return svc.batch_update_rules(db, items, updated_by=user.id)


@router.post("/incentive-rules/batch-delete", response_model=dict)
def batch_delete_incentive_rules(
    payload: IncentiveRuleBatchDeleteIn,
    db: DbSession,
    user: AdminUser,
) -> dict:
    """Batch delete multiple incentive rules. Admin only."""
    count = svc.batch_delete_rules(db, payload.ids, hard=payload.hard, updated_by=user.id)
    return {"deleted_count": count, "ids": payload.ids}


@router.get("/incentive-rules/{rule_id}", response_model=IncentiveRuleMasterOut)
def get_incentive_rule(
    rule_id: int,
    db: DbSession,
    _user: AdminUser,
) -> IncentiveRuleMasterOut:
    """Retrieve a single incentive rule by ID. Admin only."""
    rule = svc.get_rule(db, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incentive rule not found")
    return rule


@router.post("/incentive-rules", response_model=IncentiveRuleMasterOut, status_code=status.HTTP_201_CREATED)
def create_incentive_rule(
    payload: IncentiveRuleMasterIn,
    db: DbSession,
    user: AdminUser,
) -> IncentiveRuleMasterOut:
    """Create a new incentive rule. Admin only."""
    rule = svc.create_rule(db, payload, created_by=user.id)
    db.commit()
    refreshed = svc.get_rule(db, rule.id)
    return refreshed or rule


@router.put("/incentive-rules/{rule_id}", response_model=IncentiveRuleMasterOut)
def update_incentive_rule(
    rule_id: int,
    payload: IncentiveRuleMasterUpdate,
    db: DbSession,
    user: AdminUser,
) -> IncentiveRuleMasterOut:
    """Update an existing incentive rule. Admin only."""
    rule = svc.update_rule(db, rule_id, payload, updated_by=user.id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incentive rule not found")
    db.commit()
    refreshed = svc.get_rule(db, rule_id)
    return refreshed or rule


@router.patch("/incentive-rules/{rule_id}/toggle", response_model=IncentiveRuleMasterOut)
def toggle_incentive_rule(
    rule_id: int,
    db: DbSession,
    user: AdminUser,
) -> IncentiveRuleMasterOut:
    """Activate or deactivate an incentive rule. Admin only."""
    rule = svc.toggle_active(db, rule_id, updated_by=user.id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incentive rule not found")
    db.commit()
    refreshed = svc.get_rule(db, rule_id)
    return refreshed or rule


@router.delete("/incentive-rules/{rule_id}", response_model=IncentiveRuleMasterOut)
def delete_incentive_rule(
    rule_id: int,
    db: DbSession,
    user: AdminUser,
    hard: bool = False,
) -> IncentiveRuleMasterOut:
    """Soft-delete (deactivate) or hard-delete an incentive rule. Admin only."""
    existing = svc.get_rule(db, rule_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incentive rule not found")

    if hard:
        svc.hard_delete(db, rule_id)
        db.commit()
        return existing

    rule = svc.soft_delete(db, rule_id, updated_by=user.id)
    db.commit()
    refreshed = svc.get_rule(db, rule_id)
    return refreshed or rule
