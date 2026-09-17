import logging
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.routers import auth, people, parking, bookings, specialist
from app.rate_limit import limiter

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Booking API", version="1.0.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://0.0.0.0:3000",
                   "https://lphnmbg1-3000.uks1.devtunnels.ms"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
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


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
