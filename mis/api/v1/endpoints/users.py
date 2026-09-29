from datetime import datetime, timezone
import asyncio
import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mis.core.deps import require_roles
from mis.core.security import hash_password
from mis.core.constants import ONBOARD_ROLES
from mis.db.session import get_db
from mis.models import RecruiterManagerMapping, User
from mis.models.password_reset import PasswordResetToken
from mis.schemas.user import ResetPasswordRequest, UserCreate, UserListItem, UserUpdate
from mis.services.helpers import (
    find_user_by_name,
    resolve_onboarding_organization,
    resolve_organization,
    resolve_role,
    user_to_list_item,
)
from mis.services.invitation_service import (
    create_invitation_token,
    generate_invitation_for_user,
    send_invitation_email,
)
from mis.services.audit_service import user_audit_snapshot, write_audit_log

router = APIRouter()

AdminUser = Annotated[User, Depends(require_roles("MIS"))]
INVITE_EMAIL_BATCH_SIZE = 10


async def _resolve_onboarding_org_id(db: AsyncSession, role_code: str, name: str | None) -> int | None:
    if role_code not in ONBOARD_ROLES:
        return None
    if not name or not name.strip():
        raise HTTPException(
            status_code=400,
            detail="Onboarding organization is required for Onboard Team users",
        )
    try:
        onboard_org = await resolve_onboarding_organization(db, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return onboard_org.id


def _csv_value(row: dict, *aliases: str) -> str:
    normalized = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for alias in aliases:
        value = normalized.get(alias.strip().lower())
        if value:
            return value
    return ""


async def _upsert_manager_mapping(
    db: AsyncSession,
    *,
    recruiter_id: int,
    organization_id: int,
    manager: User | None,
    actor_id: int | None,
) -> None:
    if not manager:
        return

    existing = await db.execute(
        select(RecruiterManagerMapping).where(
            RecruiterManagerMapping.recruiter_id == recruiter_id,
            RecruiterManagerMapping.is_active.is_(True),
        )
    )
    for mapping in existing.scalars().all():
        mapping.is_active = False

    db.add(
        RecruiterManagerMapping(
            recruiter_id=recruiter_id,
            manager_id=manager.id,
            organization_id=organization_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )


@router.get("", response_model=list[UserListItem])
async def get_users(
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
    role: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
):
    stmt = (
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(User.deleted_at.is_(None))
        .order_by(User.full_name)
    )
    if not _admin.is_super_admin:
        stmt = stmt.where(User.organization_id == _admin.organization_id)

    if role:
        code = role.strip().upper()
        stmt = stmt.join(User.role).where(User.role.has(code=code))

    if status_filter:
        status_val = status_filter.strip().lower()
        if status_val in {"active", "disabled"}:
            stmt = stmt.where(User.is_active == (status_val == "active"))

    if search:
        q = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.full_name).like(q),
                func.lower(User.email).like(q),
                func.lower(User.team_name).like(q),
            )
        )

    result = await db.execute(stmt)
    users = result.scalars().all()
    return [await user_to_list_item(db, u) for u in users]


@router.post("", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, admin: AdminUser, db: AsyncSession = Depends(get_db)):
    try:
        org = await resolve_organization(db, body.organization)
        role = await resolve_role(db, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = await db.execute(
        select(User).where(
            func.lower(User.email) == body.email.lower(),
            User.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already exists")

    onboard_org_id = await _resolve_onboarding_org_id(
        db, role.code, body.onboarding_organization
    )

    user = User(
        organization_id=org.id,
        role_id=role.id,
        onboarding_organization_id=onboard_org_id,
        full_name=body.full_name.strip(),
        email=body.email.lower(),
        team_name=body.team or None,
        password_hash=None,
        is_active=False,
        is_super_admin=role.code == "MIS",
        created_by=admin.id if admin else None,
    )
    db.add(user)
    await db.flush()

    manager = None
    if body.manager_id:
        manager = await db.get(User, body.manager_id)
    elif body.manager_name:
        manager = await find_user_by_name(db, body.manager_name)

    if role.code in {"RECRUITER", "TEAM_LEAD"}:
        await _upsert_manager_mapping(
            db,
            recruiter_id=user.id,
            organization_id=org.id,
            manager=manager,
            actor_id=admin.id if admin else None,
        )

    await db.commit()
    await db.refresh(user, ["role", "organization"])

    try:
        await generate_invitation_for_user(db, user)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive API guard
        raise HTTPException(
            status_code=502,
            detail="Unable to send invitation email. Please try again later.",
        ) from exc

    return await user_to_list_item(db, user)


@router.get("/{user_id}", response_model=UserListItem)
async def get_user(user_id: int, _admin: AdminUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(
            User.id == user_id,
            User.deleted_at.is_(None),
            (User.organization_id == _admin.organization_id) if not _admin.is_super_admin else True,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await user_to_list_item(db, user)


@router.put("/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: int,
    body: UserUpdate,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(
            User.id == user_id,
            User.deleted_at.is_(None),
            (User.organization_id == admin.organization_id) if not admin.is_super_admin else True,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before = user_audit_snapshot(user)

    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.email is not None:
        user.email = body.email.lower()
    if body.team is not None:
        user.team_name = body.team or None
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)

    if body.organization is not None:
        try:
            org = await resolve_organization(db, body.organization)
            user.organization_id = org.id
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.role is not None:
        try:
            role = await resolve_role(db, body.role)
            # Only super admins can assign the MIS role or promote to super admin.
            # HR admins are blocked from privilege escalation.
            if role.code == "MIS" and not admin.is_super_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only Super Admins can assign the MIS role",
                )
            user.role_id = role.id
            user.is_super_admin = role.code == "MIS"
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Refresh role after potential update for onboarding-org rules
    await db.refresh(user, ["role"])

    if body.onboarding_organization is not None or (
        body.role is not None and user.role.code in ONBOARD_ROLES
    ):
        if user.role.code in ONBOARD_ROLES:
            user.onboarding_organization_id = await _resolve_onboarding_org_id(
                db, user.role.code, body.onboarding_organization
            )
        else:
            user.onboarding_organization_id = None

    manager = None
    if body.manager_id:
        manager = await db.get(User, body.manager_id)
    elif body.manager_name:
        manager = await find_user_by_name(db, body.manager_name)

    if user.role.code in {"RECRUITER", "TEAM_LEAD"} and (body.manager_id or body.manager_name):
        await _upsert_manager_mapping(
            db,
            recruiter_id=user.id,
            organization_id=user.organization_id,
            manager=manager,
            actor_id=admin.id if admin else None,
        )

    user.updated_by = admin.id if admin else None
    await db.flush()
    await write_audit_log(
        db,
        actor_id=admin.id,
        organization_id=user.organization_id,
        entity_type="USER",
        entity_id=user.id,
        action="UPDATE",
        before_json=before,
        after_json=user_audit_snapshot(user),
    )
    await db.commit()
    await db.refresh(user, ["role", "organization"])
    return await user_to_list_item(db, user)


@router.post("/{user_id}/resend-invitation")
async def resend_invitation(user_id: int, admin: AdminUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            (User.organization_id == admin.organization_id) if not admin.is_super_admin else True,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await generate_invitation_for_user(db, user)
    return {"message": f"Invitation email sent to {user.email}"}


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    body: ResetPasswordRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            (User.organization_id == admin.organization_id) if not admin.is_super_admin else True,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Block HR admins from resetting a super admin's password (privilege escalation via account takeover).
    if user.is_super_admin and not admin.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to reset this user's password",
        )

    password = (body.password or "").strip()
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.password_hash = hash_password(password)
    # Admin-set password should allow immediate login (invite-pending users are inactive)
    user.is_active = True
    user.updated_by = admin.id

    # Invalidate outstanding invite / forgot-password tokens after admin sets password
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )

    await db.commit()
    return {"message": "Password updated", "isActive": True}


@router.delete("/{user_id}")
async def delete_user(user_id: int, admin: AdminUser, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            (User.organization_id == admin.organization_id) if not admin.is_super_admin else True,
        )
    )
    if not user or user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="User not found")
    before = user_audit_snapshot(user)
    # Soft-disable only — keep row visible as Disabled after reload
    user.is_active = False
    user.updated_by = admin.id
    await write_audit_log(
        db,
        actor_id=admin.id,
        organization_id=user.organization_id,
        entity_type="USER",
        entity_id=user.id,
        action="DISABLE",
        before_json=before,
        after_json=user_audit_snapshot(user),
    )
    await db.commit()
    return {"message": "User disabled"}


# Maximum allowed upload size for user import (10 MB)
_IMPORT_MAX_SIZE_BYTES = 10 * 1024 * 1024
_ALLOWED_IMPORT_EXTENSIONS = {".csv", ".xlsx"}
_ALLOWED_IMPORT_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",  # some clients send this for xlsx
}


@router.post("/import")
async def import_users(
    admin: AdminUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    import pandas as pd

    # --- File validation ---
    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_IMPORT_EXTENSIONS if filename.endswith(e)), None)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_IMPORT_EXTENSIONS)}",
        )
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type and content_type not in _ALLOWED_IMPORT_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file content type",
        )

    # Read with size guard — avoid reading entire multi-GB uploads into memory.
    content = await file.read(_IMPORT_MAX_SIZE_BYTES + 1)
    if len(content) > _IMPORT_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {_IMPORT_MAX_SIZE_BYTES // 1024 // 1024} MB",
        )

    try:
        if ext == ".xlsx":
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    df = df.fillna("").astype(str)
    reader = df.to_dict("records")
    created = 0
    errors: list[str] = []
    pending_invites: list[tuple[User, str]] = []

    for index, row in enumerate(reader, start=2):
        full_name = _csv_value(row, "name", "full name", "fullname", "full_name")
        email = _csv_value(row, "email", "work email", "work_email").lower()
        organization = _csv_value(row, "organization")
        role = _csv_value(row, "role") or "Recruiter"
        team = _csv_value(row, "team")
        manager_name = _csv_value(row, "manager")
        onboarding_org_name = _csv_value(
            row, "onboarding org", "onboarding organization", "onboarding_org", "onboardingorg"
        )
        if not full_name or not email or not organization:
            errors.append(f"Row {index}: missing name, email, or organization")
            continue
        try:
            org = await resolve_organization(db, organization)
            role_row = await resolve_role(db, role)
        except ValueError as exc:
            errors.append(f"Row {index}: {exc}")
            continue

        existing = (
            await db.execute(
                select(User).where(
                    func.lower(User.email) == email,
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            errors.append(f"Row {index}: email already exists")
            continue

        try:
            onboard_org_id = await _resolve_onboarding_org_id(
                db, role_row.code, onboarding_org_name or None
            )
        except HTTPException as exc:
            errors.append(f"Row {index}: {exc.detail}")
            continue

        user = User(
            full_name=full_name,
            email=email,
            organization_id=org.id,
            role_id=role_row.id,
            onboarding_organization_id=onboard_org_id,
            team_name=team or None,
            is_active=False,
            is_super_admin=role_row.code == "MIS",
            created_by=admin.id,
        )
        db.add(user)
        await db.flush()

        manager = await find_user_by_name(db, manager_name) if manager_name else None
        if role_row.code in {"RECRUITER", "TEAM_LEAD"} and manager:
            await _upsert_manager_mapping(
                db,
                recruiter_id=user.id,
                organization_id=org.id,
                manager=manager,
                actor_id=admin.id,
            )

        try:
            raw_token = await create_invitation_token(db, user)
            pending_invites.append((user, raw_token))
        except Exception:
            errors.append(f"Row {index}: user created but invitation token failed")
            continue

        await write_audit_log(
            db,
            actor_id=admin.id,
            organization_id=org.id,
            entity_type="USER",
            entity_id=user.id,
            action="IMPORT",
            before_json=None,
            after_json=user_audit_snapshot(user),
        )
        created += 1

    await db.commit()

    # Send invitation emails in batches (faster than one-by-one in the create loop)
    for offset in range(0, len(pending_invites), INVITE_EMAIL_BATCH_SIZE):
        chunk = pending_invites[offset : offset + INVITE_EMAIL_BATCH_SIZE]
        results = await asyncio.gather(
            *[send_invitation_email(user, token) for user, token in chunk],
            return_exceptions=True,
        )
        for (user, _token), result in zip(chunk, results):
            if isinstance(result, Exception):
                errors.append(f"Invitation email failed for {user.email}")

    return {"message": f"Imported {created} users", "created": created, "errors": errors}


@router.post("/{user_id}/enable")
async def enable_user(user_id: int, admin: AdminUser, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            (User.organization_id == admin.organization_id) if not admin.is_super_admin else True,
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    user.deleted_at = None
    user.updated_by = admin.id
    await db.commit()
    return {"message": "User enabled"}


@router.get("/{user_id}/team")
async def get_user_team(user_id: int, _admin: AdminUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RecruiterManagerMapping).where(
            RecruiterManagerMapping.manager_id == user_id,
            RecruiterManagerMapping.is_active.is_(True),
        )
    )
    mappings = result.scalars().all()
    recruiters = []
    for m in mappings:
        user = await db.get(User, m.recruiter_id)
        if user and user.deleted_at is None:
            recruiters.append(await user_to_list_item(db, user))
    return recruiters
