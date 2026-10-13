from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration read from environment variables (SEC-01).

    Missing or invalid values (e.g. a JWT_SECRET shorter than 32 characters)
    raise a validation error, so the app refuses to start misconfigured.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = Field(default=60, gt=0)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
