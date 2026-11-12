"""Environment-based configuration. Every value can be set via an AURUM_* environment variable or backend/.env."""

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AURUM_", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://aurumtrace:aurumtrace_dev@localhost:5433/aurumtrace"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    # comma-separated in env, e.g. AURUM_CORS_ORIGINS=http://localhost:5173,https://app.example.com
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # open self-service sign-up (organisation + first admin). Disable outside development.
    allow_registration: bool = True
    sql_echo: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.env == "production":
            if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("AURUM_JWT_SECRET must be set to a strong secret (32+ chars) in production")
            if self.allow_registration:
                raise ValueError("AURUM_ALLOW_REGISTRATION must be false in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
