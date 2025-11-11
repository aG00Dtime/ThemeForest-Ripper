from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..core.config import Settings
from .job_store import JobStore


class CleanupThread(threading.Thread):
    """Background thread that prunes old jobs and artifacts."""

    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        *,
        interval_seconds: int = 60,
    ) -> None:
        super().__init__(daemon=True, name="job-cleanup")
        self._settings = settings
        self._store = store
        self._interval = interval_seconds
        self._stop_event = threading.Event()

    def run(self) -> None:  # noqa: D401 - Thread loop
        while not self._stop_event.wait(self._interval):
            self._prune()

    def stop(self) -> None:
        self._stop_event.set()

    def _prune(self) -> None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=self._settings.job_ttl_seconds)
        stale_jobs = self._store.list_stale_jobs(cutoff)
        for job in stale_jobs:
            job_dir: Optional[Path] = None
            if job.artifact_path:
                job_dir = job.artifact_path.parent
            else:
                job_dir = self._settings.jobs_root / job.job_id
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
            except Exception:
                pass
            self._store.remove(job.job_id)

