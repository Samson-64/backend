from sqlalchemy import (
    String, Date, Time, Enum as SAEnum, ForeignKey, DateTime, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum
import uuid


class BookingType(str, enum.Enum):
    APPOINTMENT = "APPOINTMENT"
    PARKING = "PARKING"


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[BookingType] = mapped_column(
        SAEnum(BookingType, name="booking_type"), nullable=False
    )
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    parking_space_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("parking_spaces.id", ondelete="SET NULL"), nullable=True
    )
    date: Mapped[str] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[str] = mapped_column(Time, nullable=False)
    end_time: Mapped[str] = mapped_column(Time, nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        SAEnum(BookingStatus, name="booking_status"), default=BookingStatus.PENDING, nullable=False
    )
    reference: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="bookings")
    person = relationship("Person", back_populates="bookings")
    parking_space = relationship("ParkingSpace", back_populates="bookings")

    __table_args__ = (
        Index("ix_bookings_type_status", "type", "status"),
    )
