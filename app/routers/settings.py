from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.user_setting import UserSetting
from app.schemas.settings import (
    SettingsResponse,
    SettingsUpdate,
    ProfileResponse,
    ProfileUpdate,
    PasswordChange,
)
from app.services.auth_service import (
    hash_password,
    verify_password,
    revoke_all_user_tokens,
    revoke_user_access_tokens,
)
from app.services.notification_service import get_or_create_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Pydantic field name -> settings column. camelCase in, snake_case stored.
_FIELD_MAP = {
    "language": "language",
    "timezone": "timezone",
    "defaultDurationMinutes": "default_duration_minutes",
    "preferredParkingFloor": "preferred_parking_floor",
    "notifyBookingUpdates": "notify_booking_updates",
    "notifyNewBookings": "notify_new_bookings",
    "notifyReminders": "notify_reminders",
    "reminderMinutesBefore": "reminder_minutes_before",
    "quietHoursEnabled": "quiet_hours_enabled",
    "quietHoursStart": "quiet_hours_start",
    "quietHoursEnd": "quiet_hours_end",
}


def _response(row: UserSetting) -> SettingsResponse:
    return SettingsResponse(
        language=row.language,
        timezone=row.timezone,
        defaultDurationMinutes=row.default_duration_minutes,
        preferredParkingFloor=row.preferred_parking_floor,
        notifyBookingUpdates=row.notify_booking_updates,
        notifyNewBookings=row.notify_new_bookings,
        notifyReminders=row.notify_reminders,
        reminderMinutesBefore=row.reminder_minutes_before,
        quietHoursEnabled=row.quiet_hours_enabled,
        quietHoursStart=row.quiet_hours_start,
        quietHoursEnd=row.quiet_hours_end,
    )


@router.get("", response_model=SettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _response(get_or_create_settings(db, user.id))


@router.patch("", response_model=SettingsResponse)
def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = get_or_create_settings(db, user.id)
    # `exclude_unset` distinguishes "field omitted" from "field sent as null",
    # which is what makes it possible to clear an optional value such as
    # preferredParkingFloor. A plain `is not None` check would silently drop it.
    for field, column in _FIELD_MAP.items():
        if field in data.model_fields_set:
            setattr(row, column, getattr(data, field))
    db.commit()
    db.refresh(row)
    return _response(row)


@router.patch("/profile", response_model=ProfileResponse)
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.email is not None and data.email.lower() != user.email.lower():
        existing = db.query(User).filter(User.email == data.email).first()
        if existing and existing.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        user.email = data.email.lower()

    if data.name is not None:
        user.name = data.name

    db.commit()
    db.refresh(user)
    return ProfileResponse.model_validate(user)


@router.post("/profile/password")
def change_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.currentPassword, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if verify_password(data.newPassword, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current one",
        )

    user.hashed_password = hash_password(data.newPassword)
    db.commit()

    # Access tokens are issued without an expiry (see config.py), so the
    # tokens_valid_after cutoff is the only way to end existing sessions.
    # Bumping it logs the current device out too, which is the intended
    # consequence of a password change; both clients redirect to /login.
    revoke_all_user_tokens(user.id, db)
    revoke_user_access_tokens(user, db)
    return {"detail": "Password updated. Please sign in again."}
