from pydantic import BaseModel
from typing import Optional


class NotificationResponse(BaseModel):
    id: str
    category: str
    title: str
    body: str
    bookingId: Optional[str] = None
    read: bool
    readAt: Optional[str] = None
    createdAt: str

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unreadCount: int
    total: int


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    updated: int
    unreadCount: int
