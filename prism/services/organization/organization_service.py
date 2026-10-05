"""Organization service."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from prism.models.organization.schemas import (
    DivisionCreate,
    DivisionOut,
    DivisionUpdate,
    OrganizationOut,
)
from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster
from prism.repositories.entities.organization import Division
from prism.repositories.organization import organization_repository
from prism.services.common.seed_incentive_rules import seed_rules_for_new_division


def list_organizations(db: Session) -> List[OrganizationOut]:
    """Return active organizations only (reference catalog for authorized roles)."""
    rows = organization_repository.list_organizations(db, active_only=True)
    return [OrganizationOut.model_validate(r) for r in rows]


def _get_rule_stats_by_division(db: Session) -> dict:
    """Fetch total and active rule counts grouped by division code."""
    stats = {}
    try:
        rows = (
            db.query(
                IncentiveRuleMaster.division,
                func.count(IncentiveRuleMaster.id).label("total"),
                func.sum(case((IncentiveRuleMaster.is_active.is_(True), 1), else_=0)).label("active"),
            )
            .group_by(IncentiveRuleMaster.division)
            .all()
        )
        for r in rows:
            stats[r[0]] = (int(r[1]), int(r[2] or 0))
    except Exception as e:
        pass
    return stats



def list_divisions(
    db: Session,
    organization_id: Optional[int] = None,
    active_only: bool = False,
) -> List[DivisionOut]:
    """Return divisions with aggregated rule counts."""
    if organization_id is not None:
        org = organization_repository.get_organization_by_id(db, organization_id)
        if org is None or not org.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

    rows = organization_repository.list_divisions(
        db, organization_id=organization_id, active_only=active_only
    )
    rule_stats = _get_rule_stats_by_division(db)

    results: List[DivisionOut] = []
    for r in rows:
        dto = DivisionOut.model_validate(r)
        total, active = rule_stats.get(r.code, (0, 0))
        # Ampcus Tech folder in UI covers both ampcusTechClient and ampcusTechInhouse
        dto.rules_count = total
        dto.active_rules_count = active
        results.append(dto)

    return results


def get_division(db: Session, division_id: int) -> DivisionOut:
    div = organization_repository.get_division_by_id(db, division_id)
    if not div:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Division not found")
    rule_stats = _get_rule_stats_by_division(db)
    dto = DivisionOut.model_validate(div)
    total, active = rule_stats.get(div.code, (0, 0))
    dto.rules_count = total
    dto.active_rules_count = active
    return dto


def create_division(
    db: Session,
    payload: DivisionCreate,
    user_id: Optional[int] = None,
) -> DivisionOut:
    """Create a new division with duplicate validation and optional default rule seeding."""
    clean_code = payload.code.strip()
    clean_name = payload.name.strip()

    if not clean_code or not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Division name and incentive cycle code are required.",
        )

    # 1. Validate duplicate code (case-insensitive)
    existing_code = (
        db.query(Division)
        .filter(func.lower(Division.code) == clean_code.lower())
        .first()
    )
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A division with cycle code '{clean_code}' already exists.",
        )

    # 2. Validate duplicate name (case-insensitive)
    existing_name = (
        db.query(Division)
        .filter(func.lower(Division.name) == clean_name.lower())
        .first()
    )
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A division with name '{clean_name}' already exists.",
        )

    # 3. Create Division entity
    org_id = payload.organization_id or 1
    calculation_engine = (payload.calculation_engine or "MARGIN_SLABS_PRO_RATA").strip()

    div = organization_repository.create_division(
        db=db,
        organization_id=org_id,
        code=clean_code,
        name=clean_name,
        description=payload.description.strip() if payload.description else None,
        calculation_engine=calculation_engine,
        is_active=payload.is_active,
    )

    # 4. Optionally seed default rules
    rules_seeded = 0
    if payload.seed_default_rules:
        rules_seeded = seed_rules_for_new_division(
            db=db,
            division_code=div.code,
            calculation_engine=calculation_engine,
        )

    db.commit()
    db.refresh(div)

    dto = DivisionOut.model_validate(div)
    dto.rules_count = rules_seeded
    dto.active_rules_count = rules_seeded
    return dto


def update_division(
    db: Session,
    division_id: int,
    payload: DivisionUpdate,
    user_id: Optional[int] = None,
) -> DivisionOut:
    div = organization_repository.get_division_by_id(db, division_id)
    if not div:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Division not found")

    if payload.name is not None:
        clean_name = payload.name.strip()
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Division name cannot be empty.",
            )
        existing_name = (
            db.query(Division)
            .filter(func.lower(Division.name) == clean_name.lower(), Division.id != division_id)
            .first()
        )
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A division with name '{clean_name}' already exists.",
            )
        div.name = clean_name

    if payload.description is not None:
        div.description = payload.description.strip() if payload.description else None

    if payload.calculation_engine is not None:
        div.calculation_engine = payload.calculation_engine.strip()

    if payload.is_active is not None:
        div.is_active = payload.is_active

    db.commit()
    db.refresh(div)

    rule_stats = _get_rule_stats_by_division(db)
    dto = DivisionOut.model_validate(div)
    total, active = rule_stats.get(div.code, (0, 0))
    dto.rules_count = total
    dto.active_rules_count = active
    return dto


def toggle_division(
    db: Session,
    division_id: int,
    user_id: Optional[int] = None,
) -> DivisionOut:
    div = organization_repository.get_division_by_id(db, division_id)
    if not div:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Division not found")

    div.is_active = not div.is_active
    db.commit()
    db.refresh(div)

    rule_stats = _get_rule_stats_by_division(db)
    dto = DivisionOut.model_validate(div)
    total, active = rule_stats.get(div.code, (0, 0))
    dto.rules_count = total
    dto.active_rules_count = active
    return dto


def delete_division(
    db: Session,
    division_id: int,
    user_id: Optional[int] = None,
) -> DivisionOut:
    div = organization_repository.get_division_by_id(db, division_id)
    if not div:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Division not found")

    core_divisions = {"nashik", "sambhajiNagar", "ampcusTechClient", "ampcusTechInhouse"}
    if div.code in core_divisions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{div.name}' is a standard core system division and cannot be deactivated or deleted.",
        )

    div.is_active = False
    db.commit()
    db.refresh(div)

    rule_stats = _get_rule_stats_by_division(db)
    dto = DivisionOut.model_validate(div)
    total, active = rule_stats.get(div.code, (0, 0))
    dto.rules_count = total
    dto.active_rules_count = active
    return dto

