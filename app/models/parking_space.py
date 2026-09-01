from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import uuid


class ParkingSpace(Base):
    __tablename__ = "parking_spaces"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[str] = mapped_column(String(50), nullable=False)

    bookings = relationship("Booking", back_populates="parking_space")
