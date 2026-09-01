import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, SessionLocal, Base
from app.models.user import User, UserRole
from app.models.person import Person
from app.models.parking_space import ParkingSpace
from app.services.auth_service import hash_password

Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    existing_users = db.query(User).count()
    if existing_users > 0:
        print("Database already seeded. Skipping.")
        sys.exit(0)

    parking_data = [
        {"name": "S-01", "location": "Level 1"},
        {"name": "S-02", "location": "Level 1"},
        {"name": "S-03", "location": "Level 1"},
        {"name": "S-04", "location": "Level 2"},
        {"name": "S-05", "location": "Level 2"},
        {"name": "S-06", "location": "Level 2"},
        {"name": "S-07", "location": "Level 3"},
        {"name": "S-08", "location": "Level 3"},
    ]
    for p in parking_data:
        space = ParkingSpace(name=p["name"], location=p["location"])
        db.add(space)

    demo_users = [
        {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "password": "password123",
            "role": UserRole.CLIENT,
        },
        {
            "name": "Carol Reyes",
            "email": "carol@example.com",
            "password": "password123",
            "role": UserRole.STAFF,
        },
    ]
    for u in demo_users:
        user = User(
            name=u["name"],
            email=u["email"],
            hashed_password=hash_password(u["password"]),
            role=u["role"],
        )
        db.add(user)

    db.commit()
    print("Database seeded successfully!")
    print("Demo accounts:")
    print("  Client: alice@example.com / password123")
    print("  Staff:  carol@example.com / password123")

finally:
    db.close()
