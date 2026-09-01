import random
import string
from datetime import date, time, datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.booking import Booking, BookingType, BookingStatus
from app.models.person import Person
from app.models.parking_space import ParkingSpace


WORKING_START = time(9, 0)
WORKING_END = time(17, 0)


def generate_reference(prefix: str) -> str:
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(random.choices(chars, k=6))}"


def time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def minutes_to_time(m: int) -> time:
    return time(m // 60, m % 60)


def format_time(t: time) -> str:
    return t.strftime("%H:%M")


def parse_time_str(t: str) -> time:
    parts = t.split(":")
    return time(int(parts[0]), int(parts[1]))


def check_slot_conflict(
    db: Session,
    date_val: date,
    start: time,
    end: time,
    exclude_booking_id: str | None = None,
    person_id: str | None = None,
    parking_space_id: str | None = None,
) -> bool:
    query = db.query(Booking).filter(
        and_(
            Booking.date == date_val,
            Booking.status.notin_([BookingStatus.CANCELLED]),
            Booking.start_time < end,
            Booking.end_time > start,
        )
    )
    if person_id:
        query = query.filter(Booking.person_id == person_id)
    elif parking_space_id:
        query = query.filter(Booking.parking_space_id == parking_space_id)
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)
    return query.first() is not None


def get_person_availability(db: Session, person_id: str, date_val: date) -> dict:
    existing = (
        db.query(Booking)
        .filter(
            and_(
                Booking.person_id == person_id,
                Booking.date == date_val,
                Booking.status.notin_([BookingStatus.CANCELLED]),
            )
        )
        .all()
    )

    return {
        "working": True,
        "schedule": {"startTime": format_time(WORKING_START), "endTime": format_time(WORKING_END)},
        "existing": [
            {"startTime": format_time(b.start_time), "endTime": format_time(b.end_time)}
            for b in existing
        ],
    }


def get_parking_availability(db: Session, space_id: str, date_val: date) -> dict:
    existing = (
        db.query(Booking)
        .filter(
            and_(
                Booking.parking_space_id == space_id,
                Booking.date == date_val,
                Booking.status.notin_([BookingStatus.CANCELLED]),
            )
        )
        .all()
    )

    return {
        "bookings": [
            {"startTime": format_time(b.start_time), "endTime": format_time(b.end_time)}
            for b in existing
        ],
    }


def create_booking(
    db: Session,
    user_id: str,
    booking_type: BookingType,
    date_val: date,
    start: time,
    end: time,
    person_id: str | None = None,
    parking_space_id: str | None = None,
) -> Booking:
    if booking_type == BookingType.APPOINTMENT:
        reference = generate_reference("MA")
        initial_status = BookingStatus.PENDING
    else:
        reference = generate_reference("PK")
        initial_status = BookingStatus.CONFIRMED

    booking = Booking(
        user_id=user_id,
        type=booking_type,
        person_id=person_id,
        parking_space_id=parking_space_id,
        date=date_val,
        start_time=start,
        end_time=end,
        status=initial_status,
        reference=reference,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def get_specialist_appointments(db: Session, person_id: str) -> list[Booking]:
    return (
        db.query(Booking)
        .filter(
            and_(
                Booking.type == BookingType.APPOINTMENT,
                Booking.person_id == person_id,
            )
        )
        .order_by(Booking.date.desc(), Booking.start_time.desc())
        .all()
    )


def update_specialist_booking_status(
    db: Session, booking_id: str, person_id: str, new_status: str
) -> Booking | None:
    booking = (
        db.query(Booking)
        .filter(
            and_(
                Booking.id == booking_id,
                Booking.type == BookingType.APPOINTMENT,
                Booking.person_id == person_id,
            )
        )
        .first()
    )
    if not booking:
        return None

    booking.status = new_status
    db.commit()
    db.refresh(booking)
    return booking
