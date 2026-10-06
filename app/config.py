from pydantic_settings import BaseSettings
from functools import lru_cache
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://root:@localhost:3306/booking"
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production-123"
    JWT_ALGORITHM: str = "HS256"
    # A value of -1 (or any value <= 0) means the token never expires: the
    # access token is then issued without an "exp" claim and the refresh token
    # gets a far-future expires_at. Users stay signed in until they log out.
    # Because never-expiring access tokens cannot be expired on their own, they
    # are instead revoked via User.tokens_valid_after (see dependencies.py).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = -1
    REFRESH_TOKEN_EXPIRE_DAYS: int = -1
    # Comma-separated list (or JSON array) of allowed CORS origins.
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://0.0.0.0:3000,https://booking.samsonmamuya41.workers.dev"
        "https://lphnmbg1-3000.uks1.devtunnels.ms"
    )
    CORS_ALLOW_ORIGIN_REGEX: str = r"http://(localhost|127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?"

    # Background ticker that raises booking reminders. Disabled in tests, where
    # lifespan runs inside TestClient and the ticker would hit the test
    # database from a background thread.
    REMINDER_SCHEDULER_ENABLED: bool = True

    class Config:
        env_file = ".env"

    @property
    def database_url(self) -> str:
        # Clever Cloud injects DATABASE_URL with a bare "mysql://" scheme.
        # SQLAlchemy needs an explicit driver, and pymysql is the installed one.
        url = self.DATABASE_URL
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+pymysql://", 1)
        return url

    @property
    def access_token_never_expires(self) -> bool:
        return self.ACCESS_TOKEN_EXPIRE_MINUTES <= 0

    @property
    def refresh_token_never_expires(self) -> bool:
        return self.REFRESH_TOKEN_EXPIRE_DAYS <= 0

    @property
    def cors_origins(self) -> list[str]:
        raw = self.CORS_ORIGINS.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                value = json.loads(raw)
                if isinstance(value, list):
                    return [str(o).strip() for o in value if str(o).strip()]
            except json.JSONDecodeError:
                pass
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
