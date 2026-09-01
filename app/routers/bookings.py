from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.person import Person
from app.models.booking import Booking, BookingType, BookingStatus
from app.schemas.booking import (
    CreateAppointment,
    AppointmentAvailability,
    BookingResponse,
    BookingListResponse,
    UpdateBookingStatus,
    PersonResponse,
    ParkingSpaceResponse,
)
from app.services.booking_service import (
    get_person_availability,
    parse_time_str,
    format_time,
    check_slot_conflict,
    create_booking,
)
from app.models.parking_space import ParkingSpace
from app.dependencies import require_staff

router = APIRouter(prefix="/api", tags=["bookings"])


def _format_booking(b: Booking) -> BookingListResponse:
    result = BookingListResponse(
        id=b.id,
        reference=b.reference,
        date=b.date.isoformat(),
        startTime=format_time(b.start_time),
        endTime=format_time(b.end_time),
        status=b.status.value,
        type=b.type.value,
    )
    if b.person:
        result.person = PersonResponse.model_validate(b.person)
    if b.parking_space:
        result.parking_space = ParkingSpaceResponse.model_validate(b.parking_space)
    result.user = {"id": b.user.id, "name": b.user.name, "email": b.user.email}
    return result


@router.get("/appointments/availability", response_model=AppointmentAvailability)
def appointment_availability(
    person_id: str,
    date: str,
    db: Session = Depends(get_db),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specialist not found")
    from datetime import date as date_type
    date_val = date_type.fromisoformat(date)
    return get_person_availability(db, person_id, date_val)


@router.post("/appointments", response_model=BookingResponse)
def book_appointment(
    data: CreateAppointment,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    person = db.query(Person).filter(Person.id == data.personId).first()
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specialist not found")

    from datetime import time, date as date_type
    date_val = date_type.fromisoformat(data.date)
    start = parse_time_str(data.startTime)
    end = parse_time_str(data.endTime)

    if start >= end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be after start time")

    WORKING_START = time(9, 0)
    WORKING_END = time(17, 0)
    if start < WORKING_START or end > WORKING_END:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment must be within working hours (09:00 - 17:00)",
        )

    has_conflict = check_slot_conflict(db, date_val, start, end, person_id=data.personId)
    if has_conflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Time slot is already booked")

    booking = create_booking(
        db,
        user_id=user.id,
        booking_type=BookingType.APPOINTMENT,
        date_val=date_val,
        start=start,
        end=end,
        person_id=data.personId,
    )

    return BookingResponse(
        id=booking.id,
        reference=booking.reference,
        date=booking.date.isoformat(),
        startTime=format_time(booking.start_time),
        endTime=format_time(booking.end_time),
        status=booking.status.value,
        type=booking.type.value,
        person=PersonResponse.model_validate(person),
    )


@router.get("/bookings", response_model=list[BookingListResponse])
def my_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bookings = (
        db.query(Booking)
        .filter(Booking.user_id == user.id)
        .order_by(Booking.date.desc(), Booking.start_time.desc())
        .all()
    )
    today = date.today()
    result = []
    for b in bookings:
        item = _format_booking(b)
        b_date = b.date if isinstance(b.date, date) else date.fromisoformat(b.date)
        if b_date >= today and b.status != BookingStatus.CANCELLED:
            item.category = "UPCOMING"
        else:
            item.category = "COMPLETED"
        result.append(item)
    return result


@router.get("/bookings/all", response_model=list[BookingListResponse])
def all_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    bookings = (
        db.query(Booking)
        .order_by(Booking.date.desc(), Booking.start_time.desc())
        .all()
    )
    today = date.today()
    result = []
    for b in bookings:
        item = _format_booking(b)
        b_date = b.date if isinstance(b.date, date) else date.fromisoformat(b.date)
        if b_date >= today and b.status != BookingStatus.CANCELLED:
            item.category = "UPCOMING"
        else:
            item.category = "COMPLETED"
        result.append(item)
    return result


@router.patch("/bookings/{booking_id}/status", response_model=BookingListResponse)
def update_booking_status(
    booking_id: str,
    data: UpdateBookingStatus,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    new_status = data.status.upper()
    valid_statuses = ["PENDING", "CONFIRMED", "COMPLETED", "CANCELLED"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of: {valid_statuses}")

    booking.status = new_status
    db.commit()
    db.refresh(booking)
    return _format_booking(booking)
