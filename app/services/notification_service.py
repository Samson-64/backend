"""Notification creation, recipient resolution and reminder generation.

Every notification is gated by the recipient's own preferences: a user who
turns a category off never gets a row written for it. Reminders additionally
respect quiet hours, because they are the only category that is a timed nudge
rather than a record of something that already happened.
"""

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.notification import Notification, NotificationCategory
from app.models.user import User, UserRole
from app.models.user_setting import UserSetting
from app.realtime import notify_notification_created

logger = logging.getLogger("uvicorn.error")

# Preference column -> notification category it gates. SYSTEM notifications are
# not user-configurable, so they are absent on purpose.
_PREFERENCE_FOR_CATEGORY = {
    NotificationCategory.BOOKING_STATUS: "notify_booking_updates",
    NotificationCategory.NEW_BOOKING: "notify_new_bookings",
    NotificationCategory.REMINDER: "notify_reminders",
}


def get_or_create_settings(db: Session, user_id: str) -> UserSetting:
    """Fetch the user's settings, inserting a default row on first access."""
    row = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
    if row is not None:
        return row
    row = UserSetting(user_id=user_id)
    db.add(row)
    # A concurrent first request can race here; the unique index on user_id is
    # the real guard, so re-read rather than trusting the insert.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        if row is None:  # pragma: no cover - only on a genuine constraint error
            raise
        return row
    db.refresh(row)
    return row


def _category_enabled(settings: UserSetting | None, category: NotificationCategory) -> bool:
    if settings is None:
        return True
    column = _PREFERENCE_FOR_CATEGORY.get(category)
    if column is None:
        return True
    return bool(getattr(settings, column))


def _in_quiet_hours(settings: UserSetting | None, when: datetime) -> bool:
    """True when ``when`` falls inside the user's quiet window.

    The window may wrap past midnight (22:00 -> 07:00), which is the common
    case, so both sides of the boundary are checked.
    """
    if settings is None or not settings.quiet_hours_enabled:
        return False
    try:
        start = time.fromisoformat(settings.quiet_hours_start)
        end = time.fromisoformat(settings.quiet_hours_end)
    except ValueError:
        return False
    now = when.time()
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


def create_notification(
    db: Session,
    user_id: str,
    category: NotificationCategory,
    title: str,
    body: str,
    booking_id: str | None = None,
    dedupe_key: str | None = None,
    push: bool = True,
) -> Notification | None:
    """Write a notification for ``user_id``, or return None if suppressed.

    The realtime push is fired only after the commit so a client can never be
    told about a row that a rollback then removed.
    """
    settings = get_or_create_settings(db, user_id)
    if not _category_enabled(settings, category):
        return None

    notification = Notification(
        user_id=user_id,
        category=category,
        title=title,
        body=body,
        booking_id=booking_id,
        dedupe_key=dedupe_key,
    )
    db.add(notification)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race on the unique dedupe index: the row already exists.
        db.rollback()
        return None
    db.refresh(notification)

    if push:
        notify_notification_created(notification)
    return notification


def _status_title(status: BookingStatus) -> str:
    return {
        BookingStatus.PENDING: "Booking received",
        BookingStatus.CONFIRMED: "Booking confirmed",
        BookingStatus.COMPLETED: "Booking completed",
        BookingStatus.CANCELLED: "Booking cancelled",
    }[status]


def _status_body(booking: Booking, status: BookingStatus) -> str:
    when = f"{booking.date.isoformat()} {booking.start_time.strftime('%H:%M')}"
    label = "Appointment" if booking.type.value == "APPOINTMENT" else "Parking"
    return f"Your {label.lower()} {booking.reference} on {when} is {status.value.lower()}."


def _recipient_ids(db: Session, booking: Booking, exclude: str | None) -> list[str]:
    """Owner, linked specialist and all staff, minus ``exclude``."""
    ids: set[str] = {booking.user_id}

    if booking.person_id:
        specialist = db.query(User.id).filter(User.person_id == booking.person_id).all()
        ids.update(row.id for row in specialist)

    staff = db.query(User.id).filter(User.role == UserRole.STAFF).all()
    ids.update(row.id for row in staff)

    if exclude:
        ids.discard(exclude)
    return sorted(ids)


def notify_booking_status_changed(
    db: Session, booking: Booking, actor_user_id: str
) -> None:
    """Tell everyone involved that ``booking`` changed status.

    The actor is excluded so staff confirming a booking do not get told about
    their own action.
    """
    status = BookingStatus(booking.status)
    for user_id in _recipient_ids(db, booking, exclude=actor_user_id):
        try:
            create_notification(
                db,
                user_id,
                NotificationCategory.BOOKING_STATUS,
                _status_title(status),
                _status_body(booking, status),
                booking_id=booking.id,
            )
        except Exception:
            # One bad recipient must not abort the rest of the fan-out.
            logger.exception("notification: status update push failed for %s", user_id)


def notify_booking_created(
    db: Session, booking: Booking, actor_user_id: str
) -> None:
    """Tell the specialist and staff that a new booking exists.

    The owner is skipped: they just created it and are looking at the result.
    """
    ids: set[str] = set()
    if booking.person_id:
        ids.update(
            row.id
            for row in db.query(User.id).filter(User.person_id == booking.person_id).all()
        )
    ids.update(
        row.id for row in db.query(User.id).filter(User.role == UserRole.STAFF).all()
    )
    ids.discard(actor_user_id)

    label = "Appointment" if booking.type.value == "APPOINTMENT" else "Parking booking"
    when = f"{booking.date.isoformat()} {booking.start_time.strftime('%H:%M')}"
    for user_id in sorted(ids):
        try:
            create_notification(
                db,
                user_id,
                NotificationCategory.NEW_BOOKING,
                f"New {label.lower()}",
                f"{booking.reference} was booked for {when}.",
                booking_id=booking.id,
            )
        except Exception:
            logger.exception("notification: new-booking push failed for %s", user_id)


def create_due_reminders(db: Session, now: datetime | None = None) -> int:
    """Create a reminder for every booking inside its reminder window.

    A booking is due when it has not started yet and starts within the user's
    ``reminder_minutes_before`` lead time.

    Returns the number of reminders written. Safe to call repeatedly: the
    dedupe key is ``reminder:<booking id>:<start>`` and carries a unique index,
    so a second pass inserts nothing. This is what makes it safe to run both
    from the background ticker and lazily on read.
    """
    now = now or datetime.now()
    created = 0

    candidates = (
        db.query(Booking)
        .filter(
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
            Booking.date >= date.today(),
        )
        .order_by(Booking.date.asc(), Booking.start_time.asc())
        .all()
    )

    for booking in candidates:
        settings = get_or_create_settings(db, booking.user_id)
        if not settings.notify_reminders:
            continue

        starts_at = datetime.combine(booking.date, booking.start_time)
        lead_end = now + timedelta(minutes=settings.reminder_minutes_before)

        if starts_at <= now:
            # Already started: too late to remind.
            continue
        if starts_at > lead_end:
            # Still further out than the lead time; a later tick will catch it.
            continue

        if _in_quiet_hours(settings, now):
            # Reminders are the one timed nudge, so they are the one category
            # quiet hours silences. Status changes are history and always kept.
            continue

        label = "Appointment" if booking.type.value == "APPOINTMENT" else "Parking booking"
        notification = create_notification(
            db,
            booking.user_id,
            NotificationCategory.REMINDER,
            f"Upcoming {label.lower()}",
            f"{booking.reference} starts at {booking.start_time.strftime('%H:%M')} on {booking.date.isoformat()}.",
            booking_id=booking.id,
            dedupe_key=f"reminder:{booking.id}:{starts_at.isoformat(timespec='minutes')}",
        )
        if notification is not None:
            created += 1

    return created
