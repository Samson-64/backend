from pydantic import BaseModel
from typing import Optional


class PersonResponse(BaseModel):
    id: str
    name: str
    position: str

    class Config:
        from_attributes = True


class ParkingSpaceResponse(BaseModel):
    id: str
    name: str
    location: str
    available: Optional[bool] = None

    class Config:
        from_attributes = True


class TimeWindow(BaseModel):
    startTime: str
    endTime: str


class ParkingAvailability(BaseModel):
    bookings: list[TimeWindow]


class CreateParkingBooking(BaseModel):
    parkingSpaceId: str
    date: str
    startTime: str
    endTime: str


class AppointmentAvailability(BaseModel):
    working: bool
    schedule: TimeWindow
    existing: list[TimeWindow]


class CreateAppointment(BaseModel):
    personId: str
    date: str
    startTime: str
    endTime: str


class BookingResponse(BaseModel):
    id: str
    reference: str
    date: str
    startTime: str
    endTime: str
    status: str
    type: str
    person: Optional[PersonResponse] = None
    parking_space: Optional[ParkingSpaceResponse] = None

    class Config:
        from_attributes = True


class BookingListResponse(BaseModel):
    id: str
    reference: str
    date: str
    startTime: str
    endTime: str
    status: str
    type: str
    category: Optional[str] = None
    person: Optional[PersonResponse] = None
    parking_space: Optional[ParkingSpaceResponse] = None
    user: Optional[dict] = None

    class Config:
        from_attributes = True


class UpdateBookingStatus(BaseModel):
    status: str
