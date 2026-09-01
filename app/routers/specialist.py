from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, require_specialist
from app.models.user import User
from app.models.booking import Booking, BookingType
from app.schemas.booking import BookingListResponse, UpdateBookingStatus, PersonResponse, ParkingSpaceResponse
from app.services.booking_service import (
    get_specialist_appointments,
    update_specialist_booking_status,
    format_time,
)

router = APIRouter(prefix="/api/specialist", tags=["specialist"])


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


@router.get("/my-appointments", response_model=list[BookingListResponse])
def my_appointments(
    db: Session = Depends(get_db),
    user: User = Depends(require_specialist),
):
    bookings = get_specialist_appointments(db, user.person_id)
    today = date.today()
    result = []
    for b in bookings:
        item = _format_booking(b)
        b_date = b.date if isinstance(b.date, date) else date.fromisoformat(b.date)
        if b_date >= today and b.status.value != "CANCELLED":
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
    user: User = Depends(require_specialist),
):
    new_status = data.status.upper()
    valid_statuses = ["PENDING", "CONFIRMED", "COMPLETED", "CANCELLED"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    booking = update_specialist_booking_status(db, booking_id, user.person_id, new_status)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found or not assigned to you",
        )
    return _format_booking(booking)
