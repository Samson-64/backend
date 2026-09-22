"""In-memory WebSocket connection registry + booking-change broadcaster.

Keeps a set of live WebSocket connections per user id (decoded from the JWT
in the /api/ws handshake). Mutating endpoints call ``notify_booking_changed``
after the DB commit so every interested client (owner, linked specialist and
all staff) re-fetches authoritative data over plain HTTP.

The broadcast coroutine is scheduled on the main asyncio loop from the
sync (threadpool-run) router handlers via ``asyncio.run_coroutine_threadsafe``.
"""

import asyncio
import logging

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.booking import Booking

logger = logging.getLogger("uvicorn.error")

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


class RealtimeManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    def connect(self, user_id: str, websocket: WebSocket) -> None:
        self._connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self._connections.pop(user_id, None)

    def user_count(self) -> int:
        return len(self._connections)

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        for ws in list(sockets):
            try:
                await ws.send_json(payload)
            except Exception:
                # Dead peer: drop it and keep broadcasting to the rest.
                self.disconnect(user_id, ws)

    async def broadcast_to_users(self, user_ids: list[str], payload: dict) -> None:
        for user_id in set(user_ids):
            await self.send_to_user(user_id, payload)


realtime = RealtimeManager()


def _recipient_ids(db: Session, booking: Booking, owner_id: str) -> list[str]:
    """Resolve every user that should hear about a change to ``booking``."""
    ids: set[str] = {owner_id}

    if booking.person_id:
        specialist = db.query(User).filter(User.person_id == booking.person_id).first()
        if specialist:
            ids.add(specialist.id)

    staff_ids = [
        row.id for row in db.query(User.id).filter(User.role == UserRole.STAFF).all()
    ]
    ids.update(staff_ids)
    return list(ids)


def notify_booking_changed(db: Session, booking: Booking, actor_user_id: str) -> None:
    """Schedule a ``booking_changed`` push to everyone who cares about ``booking``.

    Safe to call from sync FastAPI handlers (runs in a worker thread).
    """
    payload = {
        "type": "booking_changed",
        "bookingId": booking.id,
        "reference": getattr(booking, "reference", None),
        "byUserId": actor_user_id,
    }
    try:
        ids = _recipient_ids(db, booking, actor_user_id)
    except Exception:
        logger.exception("realtime: failed to resolve recipients for %s", booking.id)
        return

    loop = _main_loop
    if loop is None or loop.is_closed():
        # No live loop (e.g. tests without lifespan): push is best-effort only.
        return
    try:
        asyncio.run_coroutine_threadsafe(realtime.broadcast_to_users(ids, payload), loop)
    except RuntimeError:
        logger.exception("realtime: could not schedule broadcast for %s", booking.id)