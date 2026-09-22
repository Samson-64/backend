from pydantic_settings import BaseSettings
from functools import lru_cache
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://root:@localhost:3306/booking"
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production-123"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Comma-separated list (or JSON array) of allowed CORS origins.
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://0.0.0.0:3000,"
        "https://lphnmbg1-3000.uks1.devtunnels.ms"
    )
    CORS_ALLOW_ORIGIN_REGEX: str = r"http://(localhost|127\.0\.0\.1)(:\d+)?"

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
