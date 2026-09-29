import asyncio
import logging
from contextlib import asynccontextmanager

from starlette.middleware.base import BaseHTTPMiddleware

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.routers import auth, people, parking, bookings, specialist, realtime
from app.routers import settings as settings_router
from app.routers import notifications as notifications_router
from app.realtime import set_main_loop
from app.rate_limit import limiter
from app.config import get_settings
from app.services.reminder_scheduler import run_reminder_scheduler

logger = logging.getLogger("uvicorn.error")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Capture the event loop so sync router handlers can schedule
    # realtime WebSocket broadcasts onto it (app/realtime.py).
    loop = asyncio.get_running_loop()
    set_main_loop(loop)

    # Background reminder ticker. Off in tests: TestClient runs the lifespan,
    # and a live ticker would query the test database from another thread.
    reminder_task = None
    if settings.REMINDER_SCHEDULER_ENABLED:
        reminder_task = loop.create_task(run_reminder_scheduler())

    try:
        yield
    finally:
        if reminder_task is not None:
            reminder_task.cancel()
            try:
                await reminder_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Booking API", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request: Request, exc: OperationalError):
    logger.warning("Database unavailable during request: %s", str(exc)[:200])
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is temporarily unavailable. Please try again in a few seconds."},
    )


@app.exception_handler(SQLAlchemyTimeoutError)
async def db_pool_timeout_handler(request: Request, exc: SQLAlchemyTimeoutError):
    logger.warning("Database pool timeout during request: %s", str(exc)[:200])
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is temporarily unavailable. Please try again in a few seconds."},
    )


app.include_router(auth.router)
app.include_router(people.router)
app.include_router(parking.router)
app.include_router(bookings.router)
app.include_router(specialist.router)
app.include_router(realtime.router)
app.include_router(settings_router.router)
app.include_router(notifications_router.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
