"""Settings and notification endpoints.

Covers the defaults-on-first-read behaviour, partial updates, ownership checks,
read tracking, the preference gates, and reminder dedupe.
"""

from datetime import date, datetime, time, timedelta

from app.models.booking import Booking, BookingStatus, BookingType
from app.models.notification import Notification, NotificationCategory
from app.models.user import User
from app.models.user_setting import UserSetting
from app.services.notification_service import create_due_reminders

from conftest import TEST_PASSWORD

SETTINGS = "/api/settings"
NOTIFICATIONS = "/api/notifications"


def _login(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_settings_require_authentication(client, user):
    assert client.get(SETTINGS).status_code == 401


def test_settings_are_created_with_defaults_on_first_read(client, user, db):
    headers = _login(client)
    response = client.get(SETTINGS, headers=headers)
    assert response.status_code == 200

    body = response.json()
    assert body["language"] == "en"
    assert body["defaultDurationMinutes"] == 30
    assert body["notifyBookingUpdates"] is True
    assert body["notifyReminders"] is True
    assert body["quietHoursEnabled"] is False

    # A second read must reuse the same row, not insert a second one.
    client.get(SETTINGS, headers=headers)
    assert db.query(UserSetting).filter(UserSetting.user_id == user.id).count() == 1


def test_settings_patch_only_touches_the_fields_it_was_given(client, user):
    headers = _login(client)

    assert (
        client.patch(
            SETTINGS, json={"defaultDurationMinutes": 90}, headers=headers
        ).status_code
        == 200
    )
    body = client.patch(
        SETTINGS, json={"notifyReminders": False}, headers=headers
    ).json()

    assert body["defaultDurationMinutes"] == 90
    assert body["notifyReminders"] is False
    # Untouched fields keep their defaults.
    assert body["language"] == "en"
    assert body["notifyBookingUpdates"] is True


def test_settings_patch_can_clear_an_optional_value(client, user):
    headers = _login(client)

    set_body = client.patch(
        SETTINGS, json={"preferredParkingFloor": "Ground"}, headers=headers
    ).json()
    assert set_body["preferredParkingFloor"] == "Ground"

    # An explicit null clears it; omitting the field would leave it alone.
    cleared = client.patch(
        SETTINGS, json={"preferredParkingFloor": None}, headers=headers
    ).json()
    assert cleared["preferredParkingFloor"] is None

    client.patch(SETTINGS, json={"preferredParkingFloor": "Level 1"}, headers=headers)
    kept = client.patch(SETTINGS, json={"language": "fr"}, headers=headers).json()
    assert kept["preferredParkingFloor"] == "Level 1"


def test_settings_patch_rejects_out_of_range_values(client, user):
    headers = _login(client)
    assert (
        client.patch(
            SETTINGS, json={"defaultDurationMinutes": 5000}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.patch(
            SETTINGS, json={"quietHoursStart": "99:99"}, headers=headers
        ).status_code
        == 422
    )


def test_profile_update_changes_name(client, user):
    headers = _login(client)
    response = client.patch(
        f"{SETTINGS}/profile", json={"name": "Renamed"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


def test_profile_update_rejects_an_email_owned_by_someone_else(client, user, db):
    other = User(
        name="Other",
        email="other@example.com",
        hashed_password=user.hashed_password,
    )
    db.add(other)
    db.commit()

    headers = _login(client)
    response = client.patch(
        f"{SETTINGS}/profile", json={"email": "other@example.com"}, headers=headers
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_profile_update_allows_saving_your_own_email_unchanged(client, user):
    headers = _login(client)
    response = client.patch(
        f"{SETTINGS}/profile",
        json={"name": "Same", "email": "test@example.com"},
        headers=headers,
    )
    assert response.status_code == 200


def test_password_change_requires_the_current_password(client, user):
    headers = _login(client)
    response = client.post(
        f"{SETTINGS}/profile/password",
        json={"currentPassword": "wrong-password", "newPassword": "another-good-one"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "incorrect" in response.json()["detail"]


def test_password_change_rejects_reusing_the_current_password(client, user):
    headers = _login(client)
    response = client.post(
        f"{SETTINGS}/profile/password",
        json={"currentPassword": TEST_PASSWORD, "newPassword": TEST_PASSWORD},
        headers=headers,
    )
    assert response.status_code == 400


def test_password_change_ends_every_session_including_this_one(client, user):
    """Access tokens never expire, so the cutoff must revoke this one too."""
    headers = _login(client)
    response = client.post(
        f"{SETTINGS}/profile/password",
        json={"currentPassword": TEST_PASSWORD, "newPassword": "a-brand-new-one"},
        headers=headers,
    )
    assert response.status_code == 200

    assert client.get("/api/auth/me", headers=headers).status_code == 401


def _seed_notification(db, user, **kwargs):
    row = Notification(
        user_id=user.id,
        category=kwargs.pop("category", NotificationCategory.BOOKING_STATUS),
        title=kwargs.pop("title", "Hello"),
        body=kwargs.pop("body", "World"),
        **kwargs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_notifications_require_authentication(client, user):
    assert client.get(NOTIFICATIONS).status_code == 401


def test_empty_notification_list(client, user):
    headers = _login(client)
    response = client.get(NOTIFICATIONS, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "unreadCount": 0, "total": 0}


def test_unread_count_and_mark_read(client, user, db):
    _seed_notification(db, user)
    headers = _login(client)

    assert client.get(f"{NOTIFICATIONS}/unread-count", headers=headers).json() == {
        "count": 1
    }

    listed = client.get(NOTIFICATIONS, headers=headers).json()
    assert listed["unreadCount"] == 1
    assert listed["items"][0]["read"] is False

    notification_id = listed["items"][0]["id"]
    marked = client.patch(f"{NOTIFICATIONS}/{notification_id}/read", headers=headers)
    assert marked.status_code == 200
    assert marked.json()["read"] is True

    assert client.get(f"{NOTIFICATIONS}/unread-count", headers=headers).json() == {
        "count": 0
    }


def test_mark_read_is_idempotent(client, user, db):
    row = _seed_notification(db, user)
    headers = _login(client)

    first = client.patch(f"{NOTIFICATIONS}/{row.id}/read", headers=headers).json()
    second = client.patch(f"{NOTIFICATIONS}/{row.id}/read", headers=headers).json()
    assert first["readAt"] == second["readAt"]


def test_mark_all_read_clears_the_badge(client, user, db):
    _seed_notification(db, user)
    _seed_notification(db, user, title="Second")
    headers = _login(client)

    response = client.post(f"{NOTIFICATIONS}/read-all", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"updated": 2, "unreadCount": 0}
    assert client.get(NOTIFICATIONS, headers=headers).json()["unreadCount"] == 0


def test_unread_only_filter(client, user, db):
    _seed_notification(db, user)
    read = _seed_notification(db, user, title="Already read")
    read.read_at = datetime.now()
    db.add(read)
    db.commit()

    headers = _login(client)
    body = client.get(f"{NOTIFICATIONS}?unread_only=true", headers=headers).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Hello"


def test_delete_notification(client, user, db):
    row = _seed_notification(db, user)
    headers = _login(client)

    assert client.delete(f"{NOTIFICATIONS}/{row.id}", headers=headers).status_code == 200
    assert client.get(NOTIFICATIONS, headers=headers).json()["total"] == 0


def test_another_users_notification_is_not_reachable(client, user, db):
    stranger = User(
        name="Stranger",
        email="stranger@example.com",
        hashed_password=user.hashed_password,
    )
    db.add(stranger)
    db.commit()
    theirs = _seed_notification(db, stranger)

    headers = _login(client)
    assert client.patch(f"{NOTIFICATIONS}/{theirs.id}/read", headers=headers).status_code == 404
    assert client.delete(f"{NOTIFICATIONS}/{theirs.id}", headers=headers).status_code == 404
    assert client.get(NOTIFICATIONS, headers=headers).json()["total"] == 0


def test_status_change_notifies_owner_and_specialist_not_the_actor(client, db):
    from app.models.person import Person
    from app.services.notification_service import notify_booking_status_changed

    owner = User(name="Owner", email="owner@example.com", hashed_password="x")
    specialist = User(
        name="Spec", email="spec@example.com", hashed_password="x", role="SPECIALIST"
    )
    staff = User(name="Staff", email="staff@example.com", hashed_password="x", role="STAFF")
    person = Person(name="Spec", position="Dentist")
    db.add_all([owner, person])
    db.flush()
    specialist.person_id = person.id
    db.add_all([specialist, staff])

    booking = Booking(
        user_id=owner.id,
        type=BookingType.APPOINTMENT,
        person_id=person.id,
        date=date.today() + timedelta(days=3),
        start_time=time(10, 0),
        end_time=time(10, 30),
        status=BookingStatus.CONFIRMED,
        reference="REF-STATUS-1",
    )
    db.add(booking)
    db.commit()

    # Staff performs the update, so staff should not be told about it.
    notify_booking_status_changed(db, booking, staff.id)

    titled = {
        n.user_id: n.title
        for n in db.query(Notification).filter(Notification.booking_id == booking.id).all()
    }
    assert titled[owner.id] == "Booking confirmed"
    assert titled[specialist.id] == "Booking confirmed"
    assert staff.id not in titled


def test_disabled_category_is_never_written(client, user, db):
    from app.services.notification_service import (
        get_or_create_settings,
        notify_booking_status_changed,
    )

    settings = get_or_create_settings(db, user.id)
    settings.notify_booking_updates = False
    db.add(settings)
    db.commit()

    booking = Booking(
        user_id=user.id,
        type=BookingType.PARKING,
        date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.CANCELLED,
        reference="REF-MUTED-1",
    )
    db.add(booking)
    db.commit()

    notify_booking_status_changed(db, booking, "someone-else")
    assert db.query(Notification).count() == 0


def test_reminder_created_inside_the_window(client, user, db):
    booking = Booking(
        user_id=user.id,
        type=BookingType.APPOINTMENT,
        date=date.today(),
        start_time=(datetime.now() + timedelta(minutes=30)).time().replace(second=0, microsecond=0),
        end_time=time(23, 0),
        status=BookingStatus.CONFIRMED,
        reference="REF-REMIND-1",
    )
    db.add(booking)
    db.commit()

    assert create_due_reminders(db, now=datetime.now()) == 1
    assert create_due_reminders(db, now=datetime.now()) == 0  # deduped

    rows = db.query(Notification).all()
    assert len(rows) == 1
    assert rows[0].category == NotificationCategory.REMINDER


def test_no_reminder_for_a_booking_far_in_the_future(client, user, db):
    booking = Booking(
        user_id=user.id,
        type=BookingType.APPOINTMENT,
        date=date.today() + timedelta(days=30),
        start_time=time(10, 0),
        end_time=time(10, 30),
        status=BookingStatus.CONFIRMED,
        reference="REF-FUTURE-1",
    )
    db.add(booking)
    db.commit()

    assert create_due_reminders(db, now=datetime.now()) == 0


def test_no_reminder_for_a_cancelled_booking(client, user, db):
    booking = Booking(
        user_id=user.id,
        type=BookingType.APPOINTMENT,
        date=date.today(),
        start_time=(datetime.now() + timedelta(minutes=30)).time().replace(second=0, microsecond=0),
        end_time=time(23, 0),
        status=BookingStatus.CANCELLED,
        reference="REF-CANCELLED-1",
    )
    db.add(booking)
    db.commit()

    assert create_due_reminders(db, now=datetime.now()) == 0


def test_quiet_hours_suppress_the_reminder(client, user, db):
    now = datetime.now()
    settings = UserSetting(
        user_id=user.id,
        notify_reminders=True,
        reminder_minutes_before=60,
        quiet_hours_enabled=True,
        # A window wide enough to contain "now" whatever the time of day.
        quiet_hours_start="00:00",
        quiet_hours_end="23:59",
    )
    db.add(settings)

    booking = Booking(
        user_id=user.id,
        type=BookingType.APPOINTMENT,
        date=date.today(),
        start_time=(now + timedelta(minutes=30)).time().replace(second=0, microsecond=0),
        end_time=time(23, 59),
        status=BookingStatus.CONFIRMED,
        reference="REF-QUIET-1",
    )
    db.add(booking)
    db.commit()

    assert create_due_reminders(db, now=now) == 0


def test_reading_the_list_backfills_a_missed_reminder(client, user, db):
    """The ticker can be dead (free-tier sleep); reading must still backfill."""
    booking = Booking(
        user_id=user.id,
        type=BookingType.PARKING,
        date=date.today(),
        start_time=(datetime.now() + timedelta(minutes=20)).time().replace(second=0, microsecond=0),
        end_time=time(23, 59),
        status=BookingStatus.CONFIRMED,
        reference="REF-BACKFILL-1",
    )
    db.add(booking)
    db.commit()

    headers = _login(client)
    body = client.get(NOTIFICATIONS, headers=headers).json()

    assert body["unreadCount"] == 1
    assert body["items"][0]["category"] == "REMINDER"
