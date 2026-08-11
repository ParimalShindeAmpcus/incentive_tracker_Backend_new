from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models.user import User
from app.schemas.incentive import PaymentCreate, PaymentOut
from app.services import export_service, payment_service

router = APIRouter(tags=["reports"])


@router.get("/cycles/{cycle_id}/export")
def export_cycle(
    cycle_id: int,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
    format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
):
    data, media, filename = export_service.export_cycle(db, cycle_id, user, fmt=format)
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/payments", response_model=PaymentOut)
def create_payment(
    payload: PaymentCreate,
    db: DbSession,
    user: User = Depends(require_role("ADMIN", "ACCOUNTS")),
):
    return payment_service.pay_line(
        db,
        payload.incentive_line_id,
        user,
        payment_reference=payload.payment_reference,
        notes=payload.notes,
    )
