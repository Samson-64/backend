from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkAllReadResponse,
)
from app.services.notification_service import create_due_reminders

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _response(row: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=row.id,
        category=row.category.value,
        title=row.title,
        body=row.body,
        bookingId=row.booking_id,
        read=row.read_at is not None,
        readAt=row.read_at.isoformat() if row.read_at else None,
        createdAt=row.created_at.isoformat() if row.created_at else None,
    )


def _owned(db: Session, user: User, notification_id: str) -> Notification:
    """Fetch a notification, 404ing rather than leaking another user's rows."""
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return row


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Backfill anything that came due while the process was asleep, so a
    # free-tier host that restarted does not silently drop reminders.
    create_due_reminders(db)

    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))

    total = query.count()
    rows = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(min(limit, 200))
        .offset(max(offset, 0))
        .all()
    )
    unread = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .count()
    )
    return NotificationListResponse(
        items=[_response(r) for r in rows],
        unreadCount=unread,
        total=total,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .count()
    )
    return UnreadCountResponse(count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _owned(db, user, notification_id)
    if row.read_at is None:
        row.read_at = datetime.now()
        db.commit()
        db.refresh(row)
    return _response(row)


@router.post("/read-all", response_model=MarkAllReadResponse)
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now()
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .update({Notification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return MarkAllReadResponse(updated=updated, unreadCount=0)


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = _owned(db, user, notification_id)
    db.delete(row)
    db.commit()
    return {"detail": "Notification deleted"}
