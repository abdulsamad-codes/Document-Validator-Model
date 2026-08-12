"""Application configuration.

Centralizes all runtime configuration in a single, strongly typed
:class:`Settings` object loaded from environment variables and the ``.env``
file. Configuration values are validated by pydantic-settings at import time so
misconfiguration fails fast during application startup instead of at runtime.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

#: Default connection string when ``DATABASE_URL`` is not provided. Development
#: only; production deployments must set an explicit ``DATABASE_URL``.
_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/finance_verification"
)

#: Default public prefix under which every API route is mounted.
DEFAULT_API_PREFIX = "/api/v1"

#: Default upload storage root: ``<project_root>/storage``. Files are kept
#: outside the source tree so they never leak into version control.
_DEFAULT_UPLOAD_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage"

#: Development-only secret placeholder. Long enough to satisfy the JWT minimum
#: key length (32 bytes); production deployments must override it.
_DEV_SECRET_KEY = "change-me-in-production-32-characters-minimum"


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables.

    Attributes:
        app_name: Human-readable application name.
        environment: Deployment environment (development, testing or
            production).
        debug: Enables debug behaviour (e.g. verbose error responses). Never
            enabled in production.
        secret_key: Secret used to sign tokens and derive cryptographic keys.
        database_url: SQLAlchemy database connection string.
        log_level: Root logging level.
        api_prefix: URL prefix applied to every API router.
        upload_storage_root: Root directory under which uploaded documents are
            stored on disk.
        max_upload_size_mb: Maximum accepted size for a single uploaded file.
        confidence_threshold: Field confidence below which a critical field
            forces human review (0.0 - 1.0).
        confidence_weights: Relative weight of every confidence source. Sources
            that did not contribute to a field are ignored and the remaining
            weights are renormalized automatically.
        access_token_expire_minutes: Lifetime of a signed access-token cookie.
        refresh_token_expire_days: Lifetime of a persisted refresh token when
            the user asked the device to be remembered.
        default_employee_id: Employee id seeded by the ``app.auth.seed``
            management script.
        default_employee_email: Email seeded by the ``app.auth.seed`` script.
        default_employee_name: Display name seeded by the seed script.
        default_employee_role: Role seeded by the seed script.
        default_employee_password: Password for the seeded default account.
        bulk_queue_workers: Number of controlled queue workers to run.
        bulk_queue_max_attempts: Default retry budget for one queue job.
        bulk_queue_poll_interval: Seconds workers wait between empty polls.
        bulk_queue_retry_backoff_seconds: Base seconds for retry backoff.
        bulk_queue_stale_after_seconds: Seconds before PROCESSING jobs are
            treated as abandoned by a crashed worker.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="finance-verification-system")
    environment: Environment = Field(default="development")
    debug: bool = Field(default=False)
    secret_key: SecretStr = Field(default=SecretStr(_DEV_SECRET_KEY))
    database_url: str = Field(default=_DEFAULT_DATABASE_URL)
    log_level: LogLevel = Field(default="INFO")
    api_prefix: str = Field(default=DEFAULT_API_PREFIX)
    upload_storage_root: Path = Field(default=_DEFAULT_UPLOAD_STORAGE_ROOT)
    max_upload_size_mb: int = Field(default=25)
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    confidence_weights: dict[str, float] = Field(
        default={
            "regex": 0.50,
            "template": 0.30,
            "ocr": 0.20,
            "ai": 0.00,
        }
    )
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=30, ge=1)
    default_employee_id: str = Field(default="EMP-1001")
    default_employee_email: str = Field(default="employee@fintech.local")
    default_employee_name: str = Field(default="Employee")
    default_employee_role: str = Field(default="Verification Officer")
    default_employee_password: SecretStr = Field(
        default=SecretStr("Welcome@123"),
    )
    bulk_queue_workers: int = Field(default=2, ge=1, le=16)
    bulk_queue_max_attempts: int = Field(default=3, ge=1, le=10)
    bulk_queue_poll_interval: float = Field(default=1.0, ge=0.05, le=60.0)
    bulk_queue_retry_backoff_seconds: int = Field(default=30, ge=0)
    bulk_queue_stale_after_seconds: int = Field(default=900, ge=1)

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        """Guard against unsafe combinations for production deployments."""
        if self.environment == "production" and self.debug:
            raise ValueError("DEBUG must be false when ENVIRONMENT is production")
        if self.environment == "production" and self.secret_key.get_secret_value() == (
            _DEV_SECRET_KEY
        ):
            raise ValueError("SECRET_KEY must be overridden when ENVIRONMENT is production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Caching keeps a single configuration object for the whole process and makes
    the factory suitable for dependency injection. The cache can be cleared in
    tests by calling ``get_settings.cache_clear()``.
    """
    return Settings()
