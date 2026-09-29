from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.deps import get_current_user, require_roles
from mis.db.session import get_db
from mis.models import AppSetting, User

router = APIRouter()

DEFAULT_SETTINGS: dict[str, Any] = {
    "organizationName": "",
    "defaultCurrency": "usd",
    "fiscalYearStart": "jan",
    "jobdivaSync": True,
    "excelExportWorker": True,
    "enforceSso": False,
    "twoFactorAuth": False,
}


class SettingsUpdate(BaseModel):
    organization_name: str | None = Field(default=None, alias="organizationName")
    default_currency: str | None = Field(default=None, alias="defaultCurrency")
    fiscal_year_start: str | None = Field(default=None, alias="fiscalYearStart")
    jobdiva_sync: bool | None = Field(default=None, alias="jobdivaSync")
    excel_export_worker: bool | None = Field(default=None, alias="excelExportWorker")
    enforce_sso: bool | None = Field(default=None, alias="enforceSso")
    two_factor_auth: bool | None = Field(default=None, alias="twoFactorAuth")

    model_config = {"populate_by_name": True}


async def _load_settings(
    db: AsyncSession, organization_id: int, organization_name: str
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(AppSetting).where(
                AppSetting.organization_id == organization_id,
                AppSetting.key == "platform",
            )
        )
    ).scalar_one_or_none()
    merged = dict(DEFAULT_SETTINGS)
    merged["organizationName"] = organization_name
    if row:
        merged.update(row.value_json or {})
    return merged


@router.get("")
async def get_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await _load_settings(
        db,
        current_user.organization_id,
        current_user.organization.name if current_user.organization else "",
    )


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    current_user: Annotated[User, Depends(require_roles("MIS"))],
    db: AsyncSession = Depends(get_db),
):
    current = await _load_settings(
        db,
        current_user.organization_id,
        current_user.organization.name if current_user.organization else "",
    )
    payload = body.model_dump(exclude_none=True, by_alias=True)
    current.update(payload)

    row = (
        await db.execute(
            select(AppSetting).where(
                AppSetting.organization_id == current_user.organization_id,
                AppSetting.key == "platform",
            )
        )
    ).scalar_one_or_none()
    if row:
        row.value_json = current
        row.updated_by = current_user.id
    else:
        db.add(
            AppSetting(
                organization_id=current_user.organization_id,
                key="platform",
                value_json=current,
                updated_by=current_user.id,
            )
        )
    await db.commit()
    return current
