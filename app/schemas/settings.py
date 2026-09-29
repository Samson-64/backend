from pydantic import BaseModel, EmailStr, Field


class SettingsResponse(BaseModel):
    language: str
    timezone: str
    defaultDurationMinutes: int
    preferredParkingFloor: str | None = None
    notifyBookingUpdates: bool
    notifyNewBookings: bool
    notifyReminders: bool
    reminderMinutesBefore: int
    quietHoursEnabled: bool
    quietHoursStart: str
    quietHoursEnd: str

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    """Partial update: every field optional, unset fields are left alone."""

    language: str | None = Field(default=None, min_length=2, max_length=10)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    defaultDurationMinutes: int | None = Field(default=None, ge=5, le=480)
    preferredParkingFloor: str | None = Field(default=None, max_length=20)
    notifyBookingUpdates: bool | None = None
    notifyNewBookings: bool | None = None
    notifyReminders: bool | None = None
    reminderMinutesBefore: int | None = Field(default=None, ge=5, le=1440)
    quietHoursEnabled: bool | None = None
    quietHoursStart: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quietHoursEnd: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class ProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    person_id: str | None = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    currentPassword: str = Field(..., min_length=1, max_length=128)
    newPassword: str = Field(..., min_length=8, max_length=128)
