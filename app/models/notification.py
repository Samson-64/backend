from sqlalchemy import (
    String, Enum as SAEnum, DateTime, ForeignKey, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum
import uuid


class NotificationCategory(str, enum.Enum):
    BOOKING_STATUS = "BOOKING_STATUS"
    NEW_BOOKING = "NEW_BOOKING"
    REMINDER = "REMINDER"
    SYSTEM = "SYSTEM"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[NotificationCategory] = mapped_column(
        SAEnum(NotificationCategory, name="notification_category"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    booking_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    # Only reminders set this, so the scheduler can re-run without duplicating
    # rows after a restart. MySQL allows many NULLs in a unique index, so status
    # notifications are unaffected.
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    read_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_notifications_dedupe", "user_id", "dedupe_key", unique=True),
    )
