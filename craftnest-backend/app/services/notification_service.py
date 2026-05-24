import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, update

from app.models.notification import Notification


async def create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    type: str,
    title: str,
    body: str,
    related_id: Optional[uuid.UUID] = None,
) -> Notification:
    """
    Insert a Notification row into the database.

    This must be called *inside* an existing db.begin_nested() savepoint
    so that if the parent transaction rolls back, this notification
    is rolled back too (transactional consistency guarantee).
    """
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title[:80],
        body=body[:200],
        is_read=False,
        related_id=related_id,
    )
    db.add(notification)
    return notification


async def list_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 20,
) -> dict:
    """
    Return the latest `limit` notifications for a user and their total unread count.
    """
    # Latest notifications
    q = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(q)
    notifications = list(result.scalars().all())

    # Total unread count (not limited to 20)
    unread_q = select(func.count()).where(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    )
    unread_count = (await db.execute(unread_q)).scalar_one()

    return {"items": notifications, "unread_count": unread_count}


async def mark_notifications_read(
    db: AsyncSession,
    user_id: uuid.UUID,
    ids: Optional[list[uuid.UUID]] = None,
) -> int:
    """
    Mark notifications as read.
    If `ids` is provided and non-empty, only mark those specific IDs (owned by user_id).
    Otherwise mark ALL unread notifications for the user.
    Returns the number of rows updated.
    """
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))

    result = await db.execute(stmt)
    return result.rowcount
