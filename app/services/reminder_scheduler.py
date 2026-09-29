"""Background ticker that raises booking reminders.

A free-tier host (Render) sleeps and restarts freely, so an in-process ticker
alone is not enough to guarantee a reminder is never missed. Two things
therefore create reminders:

* this ticker, for reminders that come due while the process is up, and
* ``GET /api/notifications``, which runs the same function to backfill
  anything that came due while it was down.

Both are safe to run concurrently and repeatedly: reminders carry a dedupe key
backed by a unique index, so a duplicate insert is rejected rather than
duplicated.
"""

import asyncio
import logging

from app.database import SessionLocal
from app.services.notification_service import create_due_reminders

logger = logging.getLogger("uvicorn.error")

TICK_SECONDS = 60


async def _tick() -> None:
    while True:
        try:
            await asyncio.sleep(TICK_SECONDS)
            db = SessionLocal()
            try:
                created = await asyncio.to_thread(create_due_reminders, db)
                if created:
                    logger.info("reminders: created %d", created)
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed tick must not kill the loop; the next one will retry, and
            # the lazy backfill on read covers anything still missed.
            logger.exception("reminders: tick failed")


async def run_reminder_scheduler() -> None:
    """Entry point awaited by the app lifespan."""
    await _tick()
