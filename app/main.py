import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.routers import auth, people, parking, bookings, specialist

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Booking API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://0.0.0.0:3000",
                   "https://lphnmbg1-3000.uks1.devtunnels.ms"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
