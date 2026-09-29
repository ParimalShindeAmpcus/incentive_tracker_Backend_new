"""Secure password reset token lifecycle."""

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
    build_password_reset_email,
    send_email,
    smtp_is_configured,
)

PASSWORD_RULES = (
    (lambda p: len(p) >= 8, "Password must be at least 8 characters"),
    (lambda p: re.search(r"[A-Z]", p), "Password must contain at least one uppercase letter"),
    (lambda p: re.search(r"\d", p), "Password must contain at least one number"),
    (lambda p: re.search(r"[^A-Za-z0-9]", p), "Password must contain at least one symbol"),
)

FORGOT_PASSWORD_MESSAGE = (
    "If an account exists with this email, a password reset link has been sent."
)


def validate_password_strength(password: str) -> None:
    for rule, message in PASSWORD_RULES:
        if not rule(password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def build_reset_url(token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/reset-password#token={token}"


async def request_password_reset(db: AsyncSession, email: str) -> str:
    if not smtp_is_configured():
        logger.error("Password reset requested but SMTP is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset is temporarily unavailable. Please contact support.",
        )

    normalized = email.strip().lower()
    result = await db.execute(
        select(User).where(User.email.ilike(normalized), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return FORGOT_PASSWORD_MESSAGE

    raw_token = generate_password_reset_token()
    token_hash = hash_reset_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )

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
    await db.commit()

    reset_url = build_reset_url(raw_token)
    subject, html_body, text_body = build_password_reset_email(
        recipient_name=user.full_name,
        reset_url=reset_url,
        expire_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    )

    try:
        await send_email(
            to_email=str(user.email),
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    except EmailDeliveryError as exc:
        logger.error("Failed to send password reset email to {}: {}", user.email, exc)
        await db.execute(
            delete(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send password reset email. Please try again later.",
        ) from exc

    logger.info("Password reset email sent for user_id={}", user.id)
    return FORGOT_PASSWORD_MESSAGE


async def validate_reset_token(db: AsyncSession, token: str) -> bool:
    if not token or not token.strip():
        return False

    token_hash = hash_reset_token(token.strip())
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()
    if not record or record.used_at is not None:
        return False
    if record.expires_at < datetime.now(timezone.utc):
        return False
    return True


async def reset_password_with_token(
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

    validate_password_strength(password)

    token = token.strip()
    token_hash = hash_reset_token(token)
    result = await db.execute(
        select(PasswordResetToken, User)
        .join(User, User.id == PasswordResetToken.user_id)
        .where(PasswordResetToken.token_hash == token_hash)
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )

    record, user = row

    if not verify_reset_token(token, record.token_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )
    if record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used",
        )
    if record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired",
        )
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )

    user.password_hash = hash_password(password)
    record.used_at = datetime.now(timezone.utc)

    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != record.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    await db.commit()

    logger.info("Password reset completed for user_id={}", user.id)
    return "Password has been reset successfully."
