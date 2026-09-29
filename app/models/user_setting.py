from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import uuid


class UserSetting(Base):
    """Per-user preferences. Created lazily on the first GET /api/settings."""

    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    default_duration_minutes: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )
    preferred_parking_floor: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    # Notification categories. Each maps to one opt-in toggle in Settings.
    notify_booking_updates: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    notify_new_bookings: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    notify_reminders: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    # How far ahead of the start time a reminder is raised.
    reminder_minutes_before: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    quiet_hours_start: Mapped[str] = mapped_column(
        String(5), default="22:00", nullable=False
    )
    quiet_hours_end: Mapped[str] = mapped_column(
        String(5), default="07:00", nullable=False
    )

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
