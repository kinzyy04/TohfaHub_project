import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    body: str
    is_read: bool
    related_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationsListResponse(BaseModel):
    items: List[NotificationRead]
    unread_count: int


class ReadNotificationsRequest(BaseModel):
    """
    Optional list of notification IDs to mark as read.
    If `ids` is None or empty, ALL notifications for the user are marked read.
    """
    ids: Optional[List[uuid.UUID]] = None
