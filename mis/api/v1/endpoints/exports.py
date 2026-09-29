from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import csv
import io

from mis.api.v1.dependencies.auth import require_roles
from mis.core import rbac
from mis.db.session import get_db
from mis.models import CandidateStart, Organization, User
from mis.services.analytics_service import scope_starts_for_user

router = APIRouter()


# Characters that spreadsheet applications interpret as formula triggers (OWASP recommendation).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _sanitize_csv_value(value: object) -> object:
    """Prefix user-controlled string fields to defuse spreadsheet formula injection.

    Non-string values (int, float, date) are returned unchanged — they cannot carry formulas.
    Strings starting with a formula-trigger character are prefixed with a tab so that
    spreadsheet applications treat them as plain text.
    """
    if not isinstance(value, str):
        return value
    if value.startswith(_FORMULA_PREFIXES):
        return "\t" + value
    return value


async def _fetch_export_rows(db: AsyncSession, admin: User) -> list[dict]:
    stmt = (
        select(CandidateStart)
        .where(CandidateStart.is_deleted.is_(False))
        .order_by(CandidateStart.id.desc())
    )
    stmt = scope_starts_for_user(stmt, admin)
    starts = (await db.execute(stmt)).scalars().all()
    rows = []
    for start in starts:
        recruiter = await db.get(User, start.recruiter_id)
        org = await db.get(Organization, start.organization_id)
        rows.append(
            {
                "Start ID": start.id,
                "Activity ID": _sanitize_csv_value(start.activity_id),
                "Candidate": _sanitize_csv_value(start.candidate_name),
                "Email": _sanitize_csv_value(start.candidate_email or ""),
                "Client": _sanitize_csv_value(start.client_name or ""),
                "Job Title": _sanitize_csv_value(start.job_title or ""),
                "Start Date": start.start_date.isoformat() if start.start_date else "",
                "Margin": float(start.margin or 0),
                "Status": _sanitize_csv_value(start.status),
                "Recruiter": _sanitize_csv_value(recruiter.full_name if recruiter else ""),
                "Organization": _sanitize_csv_value(org.name if org else ""),
            }
        )
    return rows



@router.get("/excel")
async def export_excel(
    _admin: Annotated[User, Depends(require_roles(*rbac.ADMIN_ONLY))],
    db: AsyncSession = Depends(get_db),
):
    rows = await _fetch_export_rows(db, _admin)
    try:
        import pandas as pd

        buffer = io.BytesIO()
        pd.DataFrame(rows).to_excel(buffer, index=False, sheet_name="Starts")
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="starts-report.xlsx"'},
        )
    except Exception:
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        else:
            buffer.write("")
        buffer.seek(0)
        return StreamingResponse(
            io.BytesIO(buffer.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="starts-report.csv"'},
        )


@router.get("/csv")
async def export_csv(
    _admin: Annotated[User, Depends(require_roles(*rbac.ADMIN_ONLY))],
    db: AsyncSession = Depends(get_db),
):
    rows = await _fetch_export_rows(db, _admin)
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="starts-report.csv"'},
    )
