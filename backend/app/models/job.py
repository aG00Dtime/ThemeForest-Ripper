from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, HttpUrl, model_validator
from urllib.parse import urlparse


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class LogEntry:
    cursor: int
    timestamp: datetime
    level: str
    message: str


@dataclass(slots=True)
class Job:
    job_id: str
    theme_url: str
    session_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    logs: list[LogEntry] = field(default_factory=list)
    next_cursor: int = 0
    artifact_path: Optional[Path] = None
    download_size: Optional[int] = None
    error: Optional[str] = None
    expires_at: Optional[datetime] = None
    download_token: Optional[str] = None
    cancel_requested: bool = False


THEME_HOST_ALLOWLIST = ("themeforest.net", "preview.themeforest.net")


class CreateRipRequest(BaseModel):
    theme_url: HttpUrl

    @model_validator(mode="after")
    def validate_host(cls, data: "CreateRipRequest") -> "CreateRipRequest":
        host = data.theme_url.host
        if host is None or not any(host.endswith(domain) for domain in THEME_HOST_ALLOWLIST):
            raise ValueError("URL must belong to themeforest.net")
        if data.theme_url.scheme != "https":
            raise ValueError("URL must use https scheme")
        return data
    def normalize(self) -> "CreateRipRequest":
        parsed = urlparse(str(self.theme_url))
        if parsed.netloc.endswith("themeforest.net") and "full_screen_preview" not in parsed.path:
            segments = [segment for segment in parsed.path.split("/") if segment]
            try:
                item_index = segments.index("item")
                slug = segments[item_index + 1]
                item_id = segments[-1]
            except (ValueError, IndexError):
                return self
            candidate = f"https://preview.themeforest.net/item/{slug}/full_screen_preview/{item_id}"
            try:
                return CreateRipRequest(theme_url=candidate)
            except Exception:
                return self
        return self


class LogEntryDTO(BaseModel):
    cursor: int
    timestamp: datetime
    level: str
    message: str


class LogTailDTO(BaseModel):
    entries: list[LogEntryDTO]
    next_cursor: int


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    theme_url: HttpUrl
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    log_tail: LogTailDTO
    download_url: Optional[str] = None
    error: Optional[str] = None
    download_size: Optional[int] = None


class JobResponse(BaseModel):
    data: JobView


class JobLogsPayload(BaseModel):
    job_id: str
    entries: list[LogEntryDTO]
    next_cursor: int
    has_more: bool


class JobLogsResponse(BaseModel):
    data: JobLogsPayload


class CreateRipResponse(BaseModel):
    data: JobView


