"""Outbound SMTP email delivery."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger

from mis.core.config import settings


class EmailDeliveryError(Exception):
    """Raised when SMTP delivery fails."""


def smtp_is_configured() -> bool:
    return settings.smtp_is_ready


def _send_email_sync(*, to_email: str, subject: str, html_body: str, text_body: str) -> None:
    if not smtp_is_configured():
        raise EmailDeliveryError("SMTP is not configured")

    username = settings.smtp_username
    password = settings.smtp_password
    from_email = settings.smtp_from_email

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{settings.SMTP_FROM_NAME} <{from_email}>"
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                server.login(username, password)
                server.sendmail(from_email, [to_email], message.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                server.login(username, password)
                server.sendmail(from_email, [to_email], message.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        logger.error(
            "SMTP authentication failed for {}@{} — verify app password and that "
            "SMTP_USERNAME matches the Gmail account that owns the app password",
            username,
            settings.SMTP_HOST,
        )
        raise EmailDeliveryError(
            "SMTP authentication failed. Check SMTP username and app password in .env"
        ) from exc
    except Exception as exc:
        logger.exception("SMTP delivery failed for {}", to_email)
        raise EmailDeliveryError(str(exc)) from exc


async def send_email(*, to_email: str, subject: str, html_body: str, text_body: str) -> None:
    await asyncio.to_thread(
        _send_email_sync,
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )


def build_password_reset_email(*, recipient_name: str, reset_url: str, expire_minutes: int) -> tuple[str, str, str]:
    subject = "Password Reset Request"
    text_body = f"""Hello {recipient_name},

We received a request to reset your password for Starts MIS.

Reset your password using this link (expires in {expire_minutes} minutes):
{reset_url}

If you did not request this, please ignore this email. Your password will remain unchanged.

— Starts MIS Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2937; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="color: #1d4ed8; margin-bottom: 8px;">Password Reset Request</h2>
  <p>Hello {recipient_name},</p>
  <p>We received a request to reset your password for <strong>Starts MIS</strong>.</p>
  <p>Click the button below to reset your password:</p>
  <p style="margin: 28px 0;">
    <a href="{reset_url}"
       style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 999px; font-weight: 600; display: inline-block;">
      Reset Password
    </a>
  </p>
  <p style="font-size: 14px; color: #6b7280;">This link will expire in <strong>{expire_minutes} minutes</strong>.</p>
  <p style="font-size: 14px; color: #6b7280;">If you did not request this, please ignore this email. Your password will remain unchanged.</p>
  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />
  <p style="font-size: 12px; color: #9ca3af;">Starts MIS — HR &amp; Recruitment Operations</p>
</body>
</html>"""

    return subject, html_body, text_body


def build_invitation_email(*, recipient_name: str, invite_url: str, expire_hours: int) -> tuple[str, str, str]:
    app_name = settings.APP_NAME
    subject = f"You're Invited to Join {app_name}"
    text_body = f"""Hello {recipient_name},

An account has been created for you at {app_name}.

Activate your account using this link (expires in {expire_hours} hours):
{invite_url}

If you were not expecting this invitation, you may safely ignore this email.

— {app_name} Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2937; max-width: 560px; margin: 0 auto; padding: 24px;">
  <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; padding: 24px;">
    <h2 style="color: #1d4ed8; margin-top: 0; margin-bottom: 12px;">Welcome to {app_name}</h2>
    <p>Hello {recipient_name},</p>
    <p>An account has been created for you.</p>
    <p>Click the button below to activate your account and set your password.</p>
    <p style="margin: 28px 0;">
      <a href="{invite_url}"
         style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 999px; font-weight: 600; display: inline-block;">
        Accept Invitation
      </a>
    </p>
    <p style="font-size: 14px; color: #6b7280;">This invitation will expire in <strong>{expire_hours} hours</strong>.</p>
    <p style="font-size: 14px; color: #6b7280;">If you were not expecting this invitation, you may safely ignore this email.</p>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />
    <p style="font-size: 12px; color: #9ca3af;">{app_name} — HR &amp; Recruitment Operations</p>
  </div>
</body>
</html>"""

    return subject, html_body, text_body
