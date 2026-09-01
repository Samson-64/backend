from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://root:@localhost:3306/booking"
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production-123"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
