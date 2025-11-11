from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, HttpUrl, model_validator


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    logs: list[LogEntry] = field(default_factory=list)
    next_cursor: int = 0
    artifact_path: Optional[Path] = None
    error: Optional[str] = None
    expires_at: Optional[datetime] = None
    download_token: Optional[str] = None


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


