from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.config import settings
from mis.core.security import (
    generate_password_reset_token,
    hash_password,
    hash_reset_token,
    verify_reset_token,
)
from mis.models.password_reset import PasswordResetToken
from mis.models.user import User
from mis.services.email_service import (
    EmailDeliveryError,
    build_invitation_email,
    send_email,
    smtp_is_configured,
)

PASSWORD_RULES = (
    (lambda p: len(p) >= 8, "Password must be at least 8 characters"),
    (lambda p: re.search(r"[A-Z]", p), "Password must contain at least one uppercase letter"),
    (lambda p: re.search(r"\d", p), "Password must contain at least one number"),
    (lambda p: re.search(r"[^A-Za-z0-9]", p), "Password must contain at least one symbol"),
)


def generate_invitation_token() -> str:
    return generate_password_reset_token()


def validate_invitation_token(record: object | None) -> bool:
    if record is None:
        return False
    expires_at = getattr(record, "expires_at", None)
    used_at = getattr(record, "used_at", None)
    if not expires_at:
        return False
    if used_at is not None:
        return False
    return expires_at >= datetime.now(timezone.utc)


def validate_invitation_password(password: str) -> None:
    for rule, message in PASSWORD_RULES:
        if not rule(password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def build_invitation_url(token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/accept-invitation#token={token}"


async def create_invitation_token(db: AsyncSession, user: User) -> str:
    """Create an unused invitation token for the user. Does not commit or send email."""
    if not smtp_is_configured():
        logger.error("Invitation requested for user_id={} but SMTP is not configured", user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invitation is temporarily unavailable. Please contact support.",
        )

    raw_token = generate_password_reset_token()
    token_hash = hash_reset_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.INVITATION_TOKEN_EXPIRE_HOURS)

    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )

    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await db.flush()
    return raw_token


async def send_invitation_email(user: User, raw_token: str) -> None:
    """Send invitation email for an already-persisted token."""
    invite_url = build_invitation_url(raw_token)
    subject, html_body, text_body = build_invitation_email(
        recipient_name=user.full_name,
        invite_url=invite_url,
        expire_hours=settings.INVITATION_TOKEN_EXPIRE_HOURS,
    )
    try:
        await send_email(
            to_email=str(user.email),
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    except EmailDeliveryError as exc:
        logger.error("Failed to send invitation email to {}: {}", user.email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send invitation email. Please try again later.",
        ) from exc
    logger.info("Invitation email sent for user_id={}", user.id)


async def generate_invitation_for_user(db: AsyncSession, user: User) -> str:
    raw_token = await create_invitation_token(db, user)
    await db.commit()

    try:
        await send_invitation_email(user, raw_token)
    except HTTPException:
        token_hash = hash_reset_token(raw_token)
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
        await db.commit()
        raise

    return build_invitation_url(raw_token)


async def validate_invitation_token_for_db(db: AsyncSession, token: str) -> bool:
    if not token or not token.strip():
        return False

    token_hash = hash_reset_token(token.strip())
    record = (
        await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
    ).scalar_one_or_none()
    return validate_invitation_token(record)


async def accept_invitation_with_token(
    db: AsyncSession,
    *,
    token: str,
    password: str,
    confirm_password: str,
) -> str:
    if password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )

    validate_invitation_password(password)

    token = token.strip()
    token_hash = hash_reset_token(token)
    row = (
        await db.execute(
            select(PasswordResetToken, User)
            .join(User, User.id == PasswordResetToken.user_id)
            .where(PasswordResetToken.token_hash == token_hash)
        )
    ).first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation link",
        )

    record, user = row

    if not verify_reset_token(token, record.token_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation link",
        )
    if record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link has already been used",
        )
    if record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired",
        )
    if user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation link",
        )

    user.password_hash = hash_password(password)
    user.is_active = True
    record.used_at = datetime.now(timezone.utc)

    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != record.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    await db.commit()

    logger.info("Invitation accepted and account activated for user_id={}", user.id)
    return "Your account has been activated successfully."
