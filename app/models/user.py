from sqlalchemy import String, Enum as SAEnum, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum
import uuid


class UserRole(str, enum.Enum):
    CLIENT = "CLIENT"
    STAFF = "STAFF"
    SPECIALIST = "SPECIALIST"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.CLIENT, nullable=False
    )
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Access tokens do not expire (see ACCESS_TOKEN_EXPIRE_MINUTES), so logout
    # records a cutoff here instead. Any token issued before this instant is
    # rejected, which is what actually ends a session server-side.
    tokens_valid_after: Mapped[str | None] = mapped_column(DateTime, nullable=True)

    bookings = relationship("Booking", back_populates="user")
    person = relationship("Person", back_populates="users")
