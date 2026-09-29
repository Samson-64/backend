"""Shared test fixtures.

Tests run against an in-memory SQLite database, never the MySQL instance in
`.env`. The env vars below are set before any `app.*` import because
`app.config.get_settings` is lru_cached, and env vars take priority over the
values in the `.env` file.
"""

import os
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
# Point at a MySQL URL that cannot be reached. app.database builds its engine at
# import time with MySQL-only pool arguments, and SQLAlchemy engines connect
# lazily, so nothing ever dials this. Every request in the suite goes through the
# overridden get_db (or a monkeypatched SessionLocal) backed by SQLite instead.
os.environ["DATABASE_URL"] = "mysql+pymysql://unused:unused@127.0.0.1:1/unused"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
# Never-expiring sessions are the behaviour under test, so select that path
# explicitly rather than inheriting whatever the developer's .env says.
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "-1"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "-1"
# TestClient runs the app lifespan, which would start the background reminder
# ticker against the in-memory SQLite database from another thread.
os.environ["REMINDER_SCHEDULER_ENABLED"] = "false"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlalchemy.sql.functions import now as _sql_now  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base  # noqa: E402
from app.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.services.auth_service import hash_password  # noqa: E402


# The models use func.now() for server_default timestamps, which SQLite lacks.
@compiles(_sql_now, "sqlite")
def _now_sqlite(element, compiler, **kwargs):
    return "CURRENT_TIMESTAMP"


@pytest.fixture
def engine():
    # StaticPool keeps every connection on the same in-memory database.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    # The auth endpoints are rate limited (5 logins/minute) and the suite makes
    # far more than that; rate limiting is not what these tests are checking.
    limiter.enabled = False
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        limiter.enabled = True


TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def user(db):
    user = User(
        name="Test User",
        email="test@example.com",
        hashed_password=hash_password(TEST_PASSWORD),
        role=UserRole.CLIENT,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
