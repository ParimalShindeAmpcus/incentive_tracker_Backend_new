import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user, require_roles
from mis.db.session import get_db
from mis.models import (
    DropdownMaster,
    OnboardingOrganization,
    OnboardingOrganizationMapping,
    Organization,
    Role,
    Subcontractor,
    User,
)
from mis.schemas.api import DropdownItemRead, SubcontractorRead

router = APIRouter()

MASTER_ROLE_CODES = (
    "MIS",
    "RECRUITER",
    "HOD",
    "ONBOARD_TEAM",
    "MANAGER",
    "TEAM_LEAD",
    "CRM",
    "SENIOR_MANAGER",
    "ASSOCIATE_DIRECTOR",
    "DIRECTOR",
    "CENTER_HEAD",
    "AVP",
)


class MasterValueBody(BaseModel):
    value: str


class OnboardingOrgBody(BaseModel):
    value: str
    mapped_organizations: list[str] = Field(default_factory=list, alias="mappedOrganizations")

    model_config = {"populate_by_name": True}


@router.get("/dropdowns", response_model=list[DropdownItemRead])
async def get_dropdowns(
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    stmt = select(DropdownMaster).where(DropdownMaster.is_active.is_(True)).order_by(
        DropdownMaster.display_order, DropdownMaster.value
    )
    if category:
        stmt = stmt.where(DropdownMaster.category == category.upper())
    rows = (await db.execute(stmt)).scalars().all()
    return [
        DropdownItemRead(
            id=row.id,
            category=row.category,
            value=row.value,
            display_order=row.display_order,
            is_active=row.is_active,
            organization_id=row.organization_id,
        )
        for row in rows
    ]


@router.post("/dropdowns/{group}", response_model=DropdownItemRead)
async def add_dropdown_value(
    group: str,
    body: MasterValueBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    category = group.strip().upper()
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Value is required")
    row = (
        await db.execute(
            select(DropdownMaster).where(
                DropdownMaster.category == category,
                func.lower(DropdownMaster.value) == value.lower(),
            )
        )
    ).scalar_one_or_none()
    if row:
        if row.is_active:
            raise HTTPException(status_code=409, detail="Value already exists")
        row.is_active = True
        row.updated_by = current_user.id
    else:
        max_order = await db.scalar(
            select(func.coalesce(func.max(DropdownMaster.display_order), 0)).where(
                DropdownMaster.category == category
            )
        )
        row = DropdownMaster(
            category=category,
            value=value,
            display_order=int(max_order or 0) + 1,
            created_by=current_user.id,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return DropdownItemRead(
        id=row.id,
        category=row.category,
        value=row.value,
        display_order=row.display_order,
        is_active=row.is_active,
        organization_id=row.organization_id,
    )


@router.delete("/dropdowns/{group}/{item_id}")
async def remove_dropdown_value(
    group: str,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    row = await db.get(DropdownMaster, item_id)
    if not row or row.category != group.strip().upper():
        raise HTTPException(status_code=404, detail="Master value not found")
    row.is_active = False
    row.updated_by = current_user.id
    await db.commit()
    return {"message": "Master value removed"}


@router.put("/dropdowns/{group}/{item_id}", response_model=DropdownItemRead)
async def update_dropdown_value(
    group: str,
    item_id: int,
    body: MasterValueBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    row = await db.get(DropdownMaster, item_id)
    if not row or row.category != group.strip().upper() or not row.is_active:
        raise HTTPException(status_code=404, detail="Master value not found")
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Value is required")
    conflict = (
        await db.execute(
            select(DropdownMaster).where(
                DropdownMaster.category == row.category,
                func.lower(DropdownMaster.value) == value.lower(),
                DropdownMaster.id != row.id,
                DropdownMaster.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if conflict:
        raise HTTPException(status_code=409, detail="Value already exists")
    row.value = value
    row.updated_by = current_user.id
    await db.commit()
    await db.refresh(row)
    return DropdownItemRead(
        id=row.id,
        category=row.category,
        value=row.value,
        display_order=row.display_order,
        is_active=row.is_active,
        organization_id=row.organization_id,
    )


@router.get("/organizations")
async def get_organizations(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(Organization)
            .where(Organization.deleted_at.is_(None), Organization.is_active.is_(True))
            .order_by(Organization.name)
        )
    ).scalars().all()
    return [{"id": row.id, "code": row.code, "name": row.name, "isActive": True} for row in rows]


@router.get("/roles")
async def get_roles(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(select(Role).order_by(Role.id))).scalars().all()
    # Stable display order for known system roles, then custom roles by id
    order = {code: idx for idx, code in enumerate(MASTER_ROLE_CODES)}
    rows = sorted(rows, key=lambda r: (order.get(r.code, 100), r.id))
    display = {
        "MIS": "Admin",
        "RECRUITER": "Recruiter",
        "HOD": "HOD",
        "ONBOARD_TEAM": "Onboard Team",
        "MANAGER": "Manager",
        "TEAM_LEAD": "Team Lead",
        "CRM": "CRM",
        "SENIOR_MANAGER": "Senior Manager",
        "ASSOCIATE_DIRECTOR": "Associate Director",
        "DIRECTOR": "Director",
        "CENTER_HEAD": "Center Head",
        "AVP": "AVP",
    }
    return [
        {
            "id": row.id,
            "code": row.code,
            "name": display.get(row.code, row.name),
            "isActive": True,
            "isSystem": row.code in MASTER_ROLE_CODES,
        }
        for row in rows
    ]


@router.post("/roles")
async def create_role(
    body: MasterValueBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    name = body.value.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:20] or "ROLE"
    existing = (
        await db.execute(
            select(Role).where(
                or_(
                    func.lower(Role.name) == name.lower(),
                    func.upper(Role.code) == code,
                )
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Role already exists")
    next_id = int((await db.scalar(select(func.coalesce(func.max(Role.id), 0))) or 0) + 1)
    # Avoid code collisions by suffixing
    base_code = code
    suffix = 1
    while await db.scalar(select(Role.id).where(Role.code == code)):
        suffix += 1
        code = f"{base_code[: max(1, 20 - len(str(suffix)))]}{suffix}"
    role = Role(id=next_id, code=code, name=name)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return {"id": role.id, "code": role.code, "name": role.name, "isActive": True, "isSystem": False}


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    body: MasterValueBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    name = body.value.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    conflict = (
        await db.execute(
            select(Role).where(func.lower(Role.name) == name.lower(), Role.id != role.id)
        )
    ).scalar_one_or_none()
    if conflict:
        raise HTTPException(status_code=409, detail="Role already exists")
    role.name = name
    await db.commit()
    await db.refresh(role)
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "isActive": True,
        "isSystem": role.code in MASTER_ROLE_CODES,
    }


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.code in MASTER_ROLE_CODES:
        raise HTTPException(status_code=400, detail="System roles cannot be deleted")
    in_use = await db.scalar(
        select(func.count(User.id)).where(User.role_id == role.id, User.deleted_at.is_(None))
    )
    if in_use:
        raise HTTPException(status_code=400, detail="Role is assigned to users and cannot be deleted")
    await db.delete(role)
    await db.commit()
    return {"message": "Role removed"}


@router.get("/onboarding-organizations")
async def get_onboarding_organizations(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(OnboardingOrganization)
            .where(
                OnboardingOrganization.deleted_at.is_(None),
                OnboardingOrganization.is_active.is_(True),
            )
            .order_by(OnboardingOrganization.name)
        )
    ).scalars().all()
    items = []
    for row in rows:
        mapped = (
            await db.execute(
                select(Organization.name)
                .join(
                    OnboardingOrganizationMapping,
                    OnboardingOrganizationMapping.organization_id == Organization.id,
                )
                .where(
                    OnboardingOrganizationMapping.onboarding_organization_id == row.id,
                    Organization.deleted_at.is_(None),
                )
                .order_by(Organization.name)
            )
        ).scalars().all()
        items.append(
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "isActive": True,
                "mappedOrganizations": list(mapped),
            }
        )
    return items


async def _sync_onboarding_org_mappings(
    db: AsyncSession,
    *,
    onboard_org_id: int,
    mapped_names: list[str],
) -> list[str]:
    """Replace mapped legal entities for an onboarding organization. Returns resolved names."""
    existing = (
        await db.execute(
            select(OnboardingOrganizationMapping).where(
                OnboardingOrganizationMapping.onboarding_organization_id == onboard_org_id
            )
        )
    ).scalars().all()
    for row in existing:
        await db.delete(row)

    resolved_names: list[str] = []
    for raw in mapped_names:
        name = (raw or "").strip()
        if not name:
            continue
        org = (
            await db.execute(
                select(Organization).where(
                    func.lower(Organization.name) == name.lower(),
                    Organization.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=400, detail=f"Organization not found: {name}")
        db.add(
            OnboardingOrganizationMapping(
                onboarding_organization_id=onboard_org_id,
                organization_id=org.id,
            )
        )
        resolved_names.append(org.name)
    return resolved_names


@router.post("/onboarding-organizations")
async def create_onboarding_organization(
    body: OnboardingOrgBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    name = body.value.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Onboarding organization name is required")
    existing = (
        await db.execute(
            select(OnboardingOrganization).where(
                func.lower(OnboardingOrganization.name) == name.lower()
            )
        )
    ).scalar_one_or_none()
    if existing and existing.deleted_at is None and existing.is_active:
        raise HTTPException(status_code=409, detail="Onboarding organization already exists")
    if existing:
        existing.deleted_at = None
        existing.is_active = True
        existing.updated_by = current_user.id
        org = existing
    else:
        base_code = re.sub(r"[^A-Z0-9]", "", name.upper())[:16] or "ONB"
        code = base_code
        suffix = 1
        while await db.scalar(select(OnboardingOrganization.id).where(OnboardingOrganization.code == code)):
            suffix += 1
            code = f"{base_code[:16 - len(str(suffix))]}{suffix}"
        org = OnboardingOrganization(code=code, name=name, created_by=current_user.id)
        db.add(org)
    await db.flush()
    mapped = await _sync_onboarding_org_mappings(
        db, onboard_org_id=org.id, mapped_names=body.mapped_organizations
    )
    await db.commit()
    await db.refresh(org)
    return {
        "id": org.id,
        "code": org.code,
        "name": org.name,
        "isActive": True,
        "mappedOrganizations": mapped,
    }


@router.put("/onboarding-organizations/{org_id}")
async def update_onboarding_organization(
    org_id: int,
    body: OnboardingOrgBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    organization = await db.get(OnboardingOrganization, org_id)
    if not organization or organization.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Onboarding organization not found")
    name = body.value.strip()
    if name:
        organization.name = name
    organization.updated_by = current_user.id
    mapped = await _sync_onboarding_org_mappings(
        db, onboard_org_id=organization.id, mapped_names=body.mapped_organizations
    )
    await db.commit()
    await db.refresh(organization)
    return {
        "id": organization.id,
        "code": organization.code,
        "name": organization.name,
        "isActive": True,
        "mappedOrganizations": mapped,
    }


@router.delete("/onboarding-organizations/{org_id}")
async def delete_onboarding_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    organization = await db.get(OnboardingOrganization, org_id)
    if not organization or organization.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Onboarding organization not found")
    organization.is_active = False
    organization.deleted_at = func.now()
    organization.updated_by = current_user.id
    await db.commit()
    return {"message": "Onboarding organization removed"}


@router.post("/organizations")
async def create_organization(
    body: MasterValueBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    name = body.value.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Organization name is required")
    organization = (
        await db.execute(select(Organization).where(func.lower(Organization.name) == name.lower()))
    ).scalar_one_or_none()
    if organization and organization.deleted_at is None and organization.is_active:
        raise HTTPException(status_code=409, detail="Organization already exists")
    if organization:
        organization.deleted_at = None
        organization.is_active = True
        organization.updated_by = current_user.id
    else:
        base_code = re.sub(r"[^A-Z0-9]", "", name.upper())[:16] or "ORG"
        code = base_code
        suffix = 1
        while await db.scalar(select(Organization.id).where(Organization.code == code)):
            suffix += 1
            code = f"{base_code[:16-len(str(suffix))]}{suffix}"
        organization = Organization(code=code, name=name, created_by=current_user.id)
        db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return {"id": organization.id, "code": organization.code, "name": organization.name, "isActive": True}


@router.delete("/organizations/{org_id}")
async def delete_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    organization = await db.get(Organization, org_id)
    if not organization or organization.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found")
    organization.is_active = False
    organization.deleted_at = func.now()
    organization.updated_by = current_user.id
    await db.commit()
    return {"message": "Organization removed"}


@router.put("/organizations/{org_id}")
async def update_organization(
    org_id: int,
    body: MasterValueBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    organization = await db.get(Organization, org_id)
    if not organization or organization.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found")
    name = body.value.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Organization name is required")
    conflict = (
        await db.execute(
            select(Organization).where(
                func.lower(Organization.name) == name.lower(),
                Organization.id != organization.id,
                Organization.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if conflict:
        raise HTTPException(status_code=409, detail="Organization already exists")
    organization.name = name
    organization.updated_by = current_user.id
    await db.commit()
    await db.refresh(organization)
    return {
        "id": organization.id,
        "code": organization.code,
        "name": organization.name,
        "isActive": True,
    }


@router.get("/subcontractors", response_model=list[SubcontractorRead])
async def get_subcontractors(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(Subcontractor).where(
                Subcontractor.deleted_at.is_(None), Subcontractor.is_active.is_(True)
            )
        )
    ).scalars().all()
    return [
        SubcontractorRead(
            id=row.id,
            name=row.name,
            email=row.email or "",
            phone=row.contact_phone or "",
            is_active=row.is_active,
        )
        for row in rows
    ]

@router.post("/subcontractors")
async def create_subcontractor(
    body: MasterValueBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    name = body.value.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Subcontractor name is required")
    row = Subcontractor(
        name=name,
        organization_id=current_user.organization_id,
        created_by=current_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SubcontractorRead(
        id=row.id,
        name=row.name,
        email=row.email or "",
        phone=row.contact_phone or "",
        is_active=row.is_active,
    )


class SubcontractorUpdateBody(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


@router.put("/subcontractors/{sub_id}")
async def update_subcontractor(
    sub_id: int,
    body: SubcontractorUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    row = await db.get(Subcontractor, sub_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Subcontractor not found")
    if body.name is not None:
        row.name = body.name.strip()
    if body.email is not None:
        row.email = body.email.strip() or None
    if body.phone is not None:
        row.contact_phone = body.phone.strip() or None
    row.updated_by = current_user.id
    await db.commit()
    await db.refresh(row)
    return SubcontractorRead(
        id=row.id,
        name=row.name,
        email=row.email or "",
        phone=row.contact_phone or "",
        is_active=row.is_active,
    )


@router.delete("/subcontractors/{sub_id}")
async def delete_subcontractor(
    sub_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("MIS")),
):
    row = await db.get(Subcontractor, sub_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Subcontractor not found")
    row.is_active = False
    row.deleted_at = func.now()
    row.updated_by = current_user.id
    await db.commit()
    return {"message": "Subcontractor removed"}
