from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from threading import Event, Lock
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from ..models.job import Job, JobStatus, LogEntry
from .token_store import TokenStore


class JobStore:
    """In-memory storage for job state and logs."""

    def __init__(self, log_limit: int, ttl_seconds: int, token_store: TokenStore) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = Lock()
        self._log_limit = log_limit
        self._ttl_seconds = ttl_seconds
        self._tokens = token_store
        self._cancel_events: Dict[str, Event] = {}

    def _utcnow(self) -> datetime:
        return datetime.now(tz=timezone.utc)

    def create(self, theme_url: str, session_id: str) -> Job:
        now = self._utcnow()
        job = Job(
            job_id=str(uuid4()),
            theme_url=theme_url,
            session_id=session_id,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._cancel_events[job.job_id] = Event()
        return copy.deepcopy(job)

    def snapshot(self, job_id: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.deepcopy(job) if job else None

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            job = self._get(job_id)
            job.status = JobStatus.RUNNING
            job.updated_at = self._utcnow()

    def mark_succeeded(self, job_id: str, artifact_path: Path) -> None:
        size: Optional[int] = None
        if artifact_path.exists():
            size = artifact_path.stat().st_size
        if size is not None and size < 100 * 1024:
            self.mark_failed(job_id, "Final archive was too small; preview may not be rippable")
            return
        with self._lock:
            job = self._get(job_id)
            job.status = JobStatus.SUCCEEDED
            job.updated_at = self._utcnow()
            job.artifact_path = artifact_path
            job.download_size = size
            job.expires_at = job.updated_at + timedelta(seconds=self._ttl_seconds)
            job.download_token = self._tokens.issue_token(job_id, job.expires_at)

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._get(job_id)
            job.status = JobStatus.FAILED
            job.error = error
            job.updated_at = self._utcnow()
            job.expires_at = job.updated_at + timedelta(seconds=self._ttl_seconds)
            job.download_token = None
            job.download_token = self._tokens.issue_token(job_id, job.expires_at)
            job.cancel_requested = False
            job.download_size = None

    def mark_cancelled(self, job_id: str) -> None:
        with self._lock:
            job = self._get(job_id)
            job.status = JobStatus.CANCELLED
            job.updated_at = self._utcnow()
            job.cancel_requested = True
            job.artifact_path = None
            job.error = None
            job.expires_at = None
            job.download_token = None
        self._tokens.delete_for_job(job_id)

    def append_log(self, job_id: str, level: str, message: str) -> LogEntry:
        entry = LogEntry(
            cursor=0,
            timestamp=self._utcnow(),
            level=level,
            message=message,
        )
        with self._lock:
            job = self._get(job_id)
            entry.cursor = job.next_cursor
            job.logs.append(entry)
            job.next_cursor += 1
            job.updated_at = entry.timestamp
            if len(job.logs) > self._log_limit:
                job.logs = job.logs[-self._log_limit :]
        return entry

    def get_logs_since(self, job_id: str, since: int) -> tuple[list[LogEntry], int, bool]:
        with self._lock:
            job = self._get(job_id)
            entries = [log for log in job.logs if log.cursor >= since]
            truncated = bool(entries) and entries[0].cursor > since
            has_more = truncated or (bool(entries) and entries[-1].cursor < job.next_cursor - 1)
            return copy.deepcopy(entries), job.next_cursor, has_more

    def tail(self, job_id: str, limit: int) -> tuple[list[LogEntry], int]:
        with self._lock:
            job = self._get(job_id)
            entries = job.logs[-limit:]
            return copy.deepcopy(entries), job.next_cursor

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1
                for job in self._jobs.values()
                if job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
            )

    def active_job_for_session(self, session_id: str) -> Optional[Job]:
        with self._lock:
            for job in self._jobs.values():
                if job.session_id == session_id and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    return copy.deepcopy(job)
        return None

    def request_cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            event = self._cancel_events.get(job_id)
            if event is None:
                return False
            job.cancel_requested = True
            event.set()
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                job.updated_at = self._utcnow()
            return True

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(job_id)
            return event.is_set() if event else False

    def list_stale_jobs(self, cutoff: datetime) -> List[Job]:
        with self._lock:
            return [
                copy.deepcopy(job)
                for job in self._jobs.values()
                if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED) and job.updated_at <= cutoff
            ]

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            event = self._cancel_events.pop(job_id, None)
        self._tokens.delete_for_job(job_id)
        if event is not None:
            event.set()

    def _get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"Job {job_id} not found") from exc


