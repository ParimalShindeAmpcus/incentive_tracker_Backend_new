from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user, require_roles
from mis.db.session import get_db
from mis.models import EmailTemplate, User
from mis.services.email_service import send_email, smtp_is_configured

router = APIRouter()


class TemplateBody(BaseModel):
    code: str | None = None
    name: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body_html: str = Field(alias="bodyHtml", min_length=1)
    is_active: bool = Field(default=True, alias="isActive")

    model_config = {"populate_by_name": True}

    @field_validator("subject", mode="before")
    @classmethod
    def _no_crlf_in_subject(cls, v: str) -> str:
        """Reject CR/LF in the email subject to prevent SMTP header injection."""
        if isinstance(v, str) and ("\r" in v or "\n" in v):
            raise ValueError("Subject must not contain newline characters")
        return v


def _template_out(row: EmailTemplate) -> dict:
    status = "Approved" if row.is_active else "Draft"
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "subject": row.subject,
        "bodyHtml": row.body_html,
        "status": status,
        "isActive": row.is_active,
    }


@router.get("")
async def get_email_templates(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(EmailTemplate)
            .where(
                (EmailTemplate.organization_id == current_user.organization_id)
                | (EmailTemplate.organization_id.is_(None))
            )
            .order_by(EmailTemplate.name)
        )
    ).scalars().all()
    return [_template_out(row) for row in rows]


@router.get("/{template_id}")
async def get_email_template(
    template_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(EmailTemplate).where(
                EmailTemplate.id == template_id,
                (EmailTemplate.organization_id == current_user.organization_id)
                | (EmailTemplate.organization_id.is_(None)),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_out(row)


@router.post("")
async def create_email_template(
    body: TemplateBody,
    current_user: Annotated[User, Depends(require_roles("MIS"))],
    db: AsyncSession = Depends(get_db),
):
    code = (body.code or body.name.upper().replace(" ", "_"))[:50]
    row = EmailTemplate(
        organization_id=current_user.organization_id,
        code=code,
        name=body.name.strip(),
        subject=body.subject.strip(),
        body_html=body.body_html,
        is_active=body.is_active,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _template_out(row)


@router.put("/{template_id}")
async def update_email_template(
    template_id: int,
    body: TemplateBody,
    current_user: Annotated[User, Depends(require_roles("MIS"))],
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(EmailTemplate).where(
                EmailTemplate.id == template_id,
                EmailTemplate.organization_id == current_user.organization_id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    row.name = body.name.strip()
    row.subject = body.subject.strip()
    row.body_html = body.body_html
    row.is_active = body.is_active
    row.updated_by = current_user.id
    await db.commit()
    await db.refresh(row)
    return _template_out(row)


@router.post("/{template_id}/test-send")
async def send_test_email(
    template_id: int,
    current_user: Annotated[User, Depends(require_roles("MIS"))],
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(EmailTemplate).where(
                EmailTemplate.id == template_id,
                EmailTemplate.organization_id == current_user.organization_id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    if not smtp_is_configured():
        raise HTTPException(status_code=503, detail="SMTP is not configured")
    # Strip any embedded newlines from the composed subject to prevent SMTP header injection.
    safe_subject = f"[Test] {row.subject}".replace("\r", "").replace("\n", "")
    await send_email(
        to_email=str(current_user.email),
        subject=safe_subject,
        html_body=row.body_html,
        text_body=row.body_html,
    )
    return {"message": f"Test email sent to {current_user.email}"}
