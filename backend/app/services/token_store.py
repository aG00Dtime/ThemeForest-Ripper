from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional
from uuid import uuid4


class TokenStore:
    """SQLite-backed storage for download tokens."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS download_tokens (
                token TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_download_tokens_job_id ON download_tokens(job_id)"
        )
        self._conn.commit()

    def issue_token(self, job_id: str, expires_at: datetime) -> str:
        """Return an existing valid token for the job or create a new one."""
        with self._lock:
            token = self._get_valid_token(job_id, expires_at)
            if token:
                return token
            token = uuid4().hex
            self._conn.execute(
                "INSERT INTO download_tokens(token, job_id, expires_at) VALUES (?, ?, ?)",
                (token, job_id, expires_at.isoformat()),
            )
            self._conn.commit()
            return token

    def _get_valid_token(self, job_id: str, expires_at: datetime) -> Optional[str]:
        row = self._conn.execute(
            "SELECT token, expires_at FROM download_tokens WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row:
            return None
        token, stored_expiry = row
        expiry_dt = datetime.fromisoformat(stored_expiry)
        if expiry_dt >= datetime.now(tz=timezone.utc):
            return token
        # Expired; replace with new record
        self._conn.execute("DELETE FROM download_tokens WHERE job_id = ?", (job_id,))
        self._conn.commit()
        return None

    def resolve(self, token: str) -> Optional[tuple[str, datetime]]:
        row = self._conn.execute(
            "SELECT job_id, expires_at FROM download_tokens WHERE token = ?", (token,)
        ).fetchone()
        if not row:
            return None
        job_id, expires_at = row
        expiry_dt = datetime.fromisoformat(expires_at)
        if expiry_dt < datetime.now(tz=timezone.utc):
            self.delete_token(token)
            return None
        return job_id, expiry_dt

    def delete_token(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM download_tokens WHERE token = ?", (token,))
            self._conn.commit()

    def delete_for_job(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM download_tokens WHERE job_id = ?", (job_id,))
            self._conn.commit()

