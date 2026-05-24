import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.routers.deps import RoleChecker
from app.schemas.notification import NotificationsListResponse, ReadNotificationsRequest
from app.services import notification_service

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

# Any authenticated user (buyer, seller, or admin) may access their notifications.
_any_role = RoleChecker(["buyer", "seller", "admin"])


@router.get(
    "",
    response_model=NotificationsListResponse,
    summary="List my latest 20 notifications with unread count",
)
async def list_my_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_any_role),
):
    """
    Returns the latest 20 notifications for the authenticated user
    and the total `unread_count` across ALL notifications (not just the 20).
    """
    result = await notification_service.list_notifications(
        db=db,
        user_id=current_user.id,
        limit=20,
    )
    return result


@router.post(
    "/read",
    status_code=status.HTTP_200_OK,
    summary="Mark notifications as read",
)
async def mark_as_read(
    body: ReadNotificationsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_any_role),
):
    """
    Mark notifications as read.

    - If `ids` is omitted or empty, **all** unread notifications are marked read.
    - If `ids` is a non-empty list, only those specific notifications are marked read
      (the user must own them — the query always filters by `user_id`).

    Returns `{"marked_read": <count>}`.
    """
    count = await notification_service.mark_notifications_read(
        db=db,
        user_id=current_user.id,
        ids=body.ids if body.ids else None,
    )
    return {"marked_read": count}
