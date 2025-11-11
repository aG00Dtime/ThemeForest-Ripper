from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import Request

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


