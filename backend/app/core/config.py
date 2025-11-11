from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    storage_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "storage",
        description="Base directory for job artifacts.",
    )
    max_workers: int = Field(
        default=2,
        ge=1,
        le=8,
        description="Maximum concurrent rip jobs.",
    )
    queue_limit: int = Field(
        default=4,
        ge=1,
        description="Maximum enqueued jobs waiting to start.",
    )
    job_log_limit: int = Field(
        default=1000,
        ge=100,
        description="Maximum number of log entries stored per job.",
    )
    job_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="How long (seconds) to retain completed jobs and artifacts.",
    )
    chromedriver_path: str | None = Field(
        default=None,
        description="Optional explicit path to chromedriver binary.",
    )
    chrome_binary_path: Path | None = Field(
        default=Path("/usr/bin/chromium"),
        description="Path to the Chromium/Chrome binary.",
    )
    headless: bool = Field(
        default=True,
        description="Run Chrome in headless mode when true.",
    )
    token_db_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / "storage" / "tokens.db",
        description="SQLite database path for download tokens.",
    )

    model_config = SettingsConfigDict(
        env_prefix="RIPPER_",
        env_file=".env",
        case_sensitive=False,
    )

    @computed_field
    @property
    def jobs_root(self) -> Path:
        """Directory containing all job-specific folders."""
        return self.storage_dir / "jobs"


@lru_cache
def get_settings() -> Settings:
    """Return application settings (cached)."""
    settings = Settings()
    ensure_directories(settings)
    return settings


def ensure_directories(settings: Settings) -> None:
    """Create required directories if they do not exist."""
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.jobs_root.mkdir(parents=True, exist_ok=True)
    settings.token_db_path.parent.mkdir(parents=True, exist_ok=True)


