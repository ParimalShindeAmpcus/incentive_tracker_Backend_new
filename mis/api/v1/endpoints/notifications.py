from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from mis.core.constants import START_NOTIFICATION_TYPES
from mis.core.deps import get_current_user
from mis.db.session import get_db
from mis.models import User

router = APIRouter()


@router.get("")
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            """
            SELECT id, candidate_start_id, type, title, message, is_read, created_at
            FROM notifications
            WHERE user_id = :user_id AND type IN :types
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).bindparams(bindparam("types", expanding=True)),
        {"user_id": current_user.id, "types": list(START_NOTIFICATION_TYPES)},
    )
    return [
        {
            "id": str(row.id),
            "candidateStartId": str(row.candidate_start_id),
            "type": row.type,
            "title": row.title,
            "message": row.message,
            "isRead": row.is_read,
            "createdAt": row.created_at,
        }
        for row in result
    ]


@router.post("/read")
async def mark_notifications_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        text(
            """
            UPDATE notifications
            SET is_read = TRUE
            WHERE user_id = :user_id
              AND type IN :types
              AND is_read = FALSE
            """
        ).bindparams(bindparam("types", expanding=True)),
        {"user_id": current_user.id, "types": list(START_NOTIFICATION_TYPES)},
    )
    await db.commit()
    return {"message": "Notifications marked as read"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        text(
            """
            DELETE FROM notifications
            WHERE id = :notification_id AND user_id = :user_id
            """
        ),
        {"notification_id": notification_id, "user_id": current_user.id},
    )
    await db.commit()
    return {"message": "Notification deleted"}
