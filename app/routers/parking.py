from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.parking_space import ParkingSpace
from app.models.booking import Booking, BookingStatus
from app.schemas.booking import (
    ParkingSpaceResponse,
    CreateParkingBooking,
    ParkingAvailability,
    BookingResponse,
)
from app.services.booking_service import (
    get_parking_availability,
    parse_time_str,
    check_slot_conflict,
    create_booking,
)

router = APIRouter(prefix="/api/parking", tags=["parking"])


def _annotate_availability(spaces: list[ParkingSpaceResponse], parking_spaces: list[ParkingSpace], date_val: date | None, db: Session) -> list[ParkingSpaceResponse]:
    if not date_val:
        return spaces
    result = []
    for ps_obj, ps_schema in zip(parking_spaces, spaces):
        bookings = (
            db.query(Booking)
            .filter(
                Booking.parking_space_id == ps_obj.id,
                Booking.date == date_val,
                Booking.status.notin_([BookingStatus.CANCELLED]),
            )
            .all()
        )
        if date_val == date.today():
            now_time = datetime.now().time()
            ps_schema.available = not any(
                b.start_time <= now_time < b.end_time for b in bookings
            )
        else:
            ps_schema.available = len(bookings) == 0
        result.append(ps_schema)
    return result


@router.get("/spaces", response_model=list[ParkingSpaceResponse])
def list_parking_spaces(
    date: str | None = None,
    db: Session = Depends(get_db),
):
    parking_spaces = db.query(ParkingSpace).all()
    spaces = [ParkingSpaceResponse.model_validate(ps) for ps in parking_spaces]
    date_val = date and __import__("datetime").date.fromisoformat(date)
    return _annotate_availability(spaces, parking_spaces, date_val, db)


@router.get("/spaces/{space_id}/availability", response_model=ParkingAvailability)
def get_space_availability(
    space_id: str,
    date: str,
    db: Session = Depends(get_db),
):
    space = db.query(ParkingSpace).filter(ParkingSpace.id == space_id).first()
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking space not found")
    date_val = __import__("datetime").date.fromisoformat(date)
    return get_parking_availability(db, space_id, date_val)


@router.post("/book", response_model=BookingResponse)
def book_parking(
    data: CreateParkingBooking,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    space = db.query(ParkingSpace).filter(ParkingSpace.id == data.parkingSpaceId).first()
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking space not found")

    date_val = __import__("datetime").date.fromisoformat(data.date)
    start = parse_time_str(data.startTime)
    end = parse_time_str(data.endTime)

    if start >= end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be after start time")

    has_conflict = check_slot_conflict(db, date_val, start, end, parking_space_id=data.parkingSpaceId)
    if has_conflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Time slot is already booked")

    booking = create_booking(
        db,
        user_id=user.id,
        booking_type="PARKING",
        date_val=date_val,
        start=start,
        end=end,
        parking_space_id=data.parkingSpaceId,
    )

    return BookingResponse(
        id=booking.id,
        reference=booking.reference,
        date=booking.date.isoformat(),
        startTime=booking.start_time.strftime("%H:%M"),
        endTime=booking.end_time.strftime("%H:%M"),
        status=booking.status.value,
        type=booking.type.value,
        parking_space=ParkingSpaceResponse.model_validate(space),
    )
