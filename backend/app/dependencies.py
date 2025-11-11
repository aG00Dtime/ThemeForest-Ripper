from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import secrets
from typing import Final

from fastapi import Request, Response

from .core.config import Settings, get_settings
from .services.job_store import JobStore
from .services.rip_runner import RipRunner
from .services.token_store import TokenStore


def get_app_settings() -> Settings:
    return get_settings()


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store  # type: ignore[attr-defined]


def get_executor(request: Request) -> ThreadPoolExecutor:
    return request.app.state.executor  # type: ignore[attr-defined]


def get_rip_runner(request: Request) -> RipRunner:
    return request.app.state.rip_runner  # type: ignore[attr-defined]


def get_token_store(request: Request) -> TokenStore:
    return request.app.state.token_store  # type: ignore[attr-defined]


SESSION_COOKIE_NAME: Final[str] = "theme_ripper_session"
SESSION_COOKIE_MAX_AGE: Final[int] = 60 * 60 * 24 * 30  # 30 days


def get_or_create_session_id(request: Request, response: Response) -> str:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is None or not _is_valid_session_id(session_id):
        session_id = secrets.token_urlsafe(32)
    secure_cookie = request.url.scheme == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=SESSION_COOKIE_MAX_AGE,
    )
    return session_id


def _is_valid_session_id(value: str) -> bool:
    if not value:
        return False
    # Basic length guard to avoid unbounded cookie values
    return len(value) <= 256


