from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, people, parking, bookings, specialist

app = FastAPI(title="Booking API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lphnmbg1-3000.uks1.devtunnels.ms"], # "http://localhost:3000", "http://0.0.0.0:3000",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(people.router)
app.include_router(parking.router)
app.include_router(bookings.router)
app.include_router(specialist.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
