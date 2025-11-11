from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI

from .api.routes import rips
from .core.config import get_settings
from .services.cleanup import CleanupThread
from .services.job_store import JobStore
from .services.rip_runner import RipRunner
from .services.token_store import TokenStore


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Theme Ripper API",
        version="0.1.0",
    )

    token_store = TokenStore(settings.token_db_path)
    job_store = JobStore(settings.job_log_limit, settings.job_ttl_seconds, token_store)
    executor = ThreadPoolExecutor(max_workers=settings.max_workers)
    rip_runner = RipRunner(settings, job_store)
    cleanup_thread = CleanupThread(settings, job_store)
    cleanup_thread.start()

    app.state.settings = settings  # type: ignore[attr-defined]
    app.state.job_store = job_store  # type: ignore[attr-defined]
    app.state.executor = executor  # type: ignore[attr-defined]
    app.state.rip_runner = rip_runner  # type: ignore[attr-defined]
    app.state.cleanup_thread = cleanup_thread  # type: ignore[attr-defined]
    app.state.token_store = token_store  # type: ignore[attr-defined]

    app.include_router(rips.router)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("shutdown")
    def shutdown() -> None:
        executor.shutdown(wait=True, cancel_futures=True)
        cleanup_thread.stop()

    return app


app = create_app()


