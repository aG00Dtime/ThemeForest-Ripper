from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from ...core.config import Settings
from ...dependencies import (
    get_app_settings,
    get_executor,
    get_job_store,
    get_rip_runner,
    get_token_store,
    get_or_create_session_id,
)
from ...models.job import (
    CreateRipRequest,
    CreateRipResponse,
    JobLogsResponse,
    JobResponse,
    JobStatus,
    JobView,
    LogEntryDTO,
    LogTailDTO,
    Job,
)
from ...services.job_store import JobStore
from ...services.rip_runner import RipRunner
from ...services.token_store import TokenStore

router = APIRouter(prefix="/v1/rips", tags=["rips"])


def _raise_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateRipResponse,
)
async def create_rip_job(
    payload: CreateRipRequest,
    request: Request,
    job_store: JobStore = Depends(get_job_store),
    executor: ThreadPoolExecutor = Depends(get_executor),
    runner: RipRunner = Depends(get_rip_runner),
    settings: Settings = Depends(get_app_settings),
    session_id: str = Depends(get_or_create_session_id),
) -> CreateRipResponse:
    if job_store.active_count() >= settings.queue_limit:
        _raise_error(status.HTTP_429_TOO_MANY_REQUESTS, "TOO_MANY_JOBS", "Job queue is full, try again later")

    active_job = job_store.active_job_for_session(session_id)
    if active_job is not None:
        _raise_error(
            status.HTTP_409_CONFLICT,
            "ACTIVE_JOB_EXISTS",
            "You already have a job running. Wait for it to finish or clear it before starting another.",
        )

    job = job_store.create(str(payload.theme_url), session_id=session_id)
    job_store.append_log(job.job_id, "info", "Job queued")

    def task() -> None:
        try:
            runner.run(job.job_id, str(payload.theme_url))
        except Exception:
            # Errors already recorded in job store; swallow to avoid choking executor.
            pass

    executor.submit(task)

    snapshot = job_store.snapshot(job.job_id)
    assert snapshot is not None
    return CreateRipResponse(data=_to_job_view(snapshot, request))


@router.get(
    "/{job_id}",
    response_model=JobResponse,
)
async def get_job(
    job_id: str,
    request: Request,
    job_store: JobStore = Depends(get_job_store),
    settings: Settings = Depends(get_app_settings),
    session_id: str = Depends(get_or_create_session_id),
) -> JobResponse:
    job = job_store.snapshot(job_id)
    if job is None:
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found")
    if job.session_id != session_id:
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found")
    return JobResponse(data=_to_job_view(job, request))


@router.get(
    "/{job_id}/logs",
    response_model=JobLogsResponse,
)
async def get_job_logs(
    job_id: str,
    since: int = Query(default=0, ge=0),
    job_store: JobStore = Depends(get_job_store),
    session_id: str = Depends(get_or_create_session_id),
) -> JobLogsResponse:
    snapshot = job_store.snapshot(job_id)
    if snapshot is None:
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found")
    if snapshot.session_id != session_id:
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found")

    entries, next_cursor, has_more = job_store.get_logs_since(job_id, since)
    return JobLogsResponse(
        data={
            "job_id": job_id,
            "entries": [_to_log_entry(e) for e in entries],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    )


@router.get(
    "/{job_id}/download",
    response_class=FileResponse,
)
async def download_job_artifact(
    job_id: str,
    job_store: JobStore = Depends(get_job_store),
    session_id: str = Depends(get_or_create_session_id),
) -> FileResponse:
    job = job_store.snapshot(job_id)
    if job is None:
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found")
    if job.session_id != session_id:
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found")
    if job.status != JobStatus.SUCCEEDED or job.artifact_path is None:
        _raise_error(status.HTTP_409_CONFLICT, "JOB_NOT_READY", "Job not completed successfully")
    if job.expires_at and job.expires_at < datetime.now(tz=timezone.utc):
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "Download link has expired")

    return FileResponse(
        path=job.artifact_path,
        media_type="application/zip",
        filename=f"{job.job_id}.zip",
    )


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_job(
    job_id: str,
    job_store: JobStore = Depends(get_job_store),
    session_id: str = Depends(get_or_create_session_id),
) -> Response:
    job = job_store.snapshot(job_id)
    if job is None or job.session_id != session_id:
        _raise_error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found")

    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        job_store.request_cancel(job_id)
        job_store.append_log(job_id, "info", "Cancellation requested by user")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    job_store.remove(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/downloads/{token}",
    response_class=FileResponse,
)
async def download_job_by_token(
    token: str,
    token_store: TokenStore = Depends(get_token_store),
    job_store: JobStore = Depends(get_job_store),
) -> FileResponse:
    resolved = token_store.resolve(token)
    if resolved is None:
        _raise_error(status.HTTP_404_NOT_FOUND, "DOWNLOAD_NOT_FOUND", "Download link is invalid or expired")
    job_id, expires_at = resolved
    job = job_store.snapshot(job_id)
    if job is None or job.status != JobStatus.SUCCEEDED or job.artifact_path is None:
        token_store.delete_token(token)
        _raise_error(status.HTTP_404_NOT_FOUND, "DOWNLOAD_NOT_FOUND", "Download link is invalid or expired")
    if expires_at < datetime.now(tz=timezone.utc):
        token_store.delete_token(token)
        _raise_error(status.HTTP_404_NOT_FOUND, "DOWNLOAD_NOT_FOUND", "Download link has expired")
    return FileResponse(
        path=job.artifact_path,
        media_type="application/zip",
        filename=f"{job.job_id}.zip",
    )


LOG_TAIL_LIMIT = 50


def _to_job_view(job: Job, request: Request) -> JobView:
    entries = job.logs[-LOG_TAIL_LIMIT:]
    next_cursor = job.next_cursor
    log_entries = [_to_log_entry(entry) for entry in entries]
    download_url: Optional[str] = None
    if (
        job.status == JobStatus.SUCCEEDED
        and job.artifact_path is not None
        and job.download_token
        and (job.expires_at is None or job.expires_at > datetime.now(tz=timezone.utc))
    ):
        raw_url = str(request.url_for("download_job_by_token", token=job.download_token))
        download_url = _apply_forwarded_headers(raw_url, request)

    return JobView(
        job_id=job.job_id,
        status=job.status,
        theme_url=job.theme_url,
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
        log_tail=LogTailDTO(entries=log_entries, next_cursor=next_cursor),
        download_url=download_url,
        download_size=job.download_size,
        error=job.error,
    )


def _to_log_entry(entry) -> LogEntryDTO:
    return LogEntryDTO(
        cursor=entry.cursor,
        timestamp=entry.timestamp,
        level=entry.level,
        message=entry.message,
    )


def _apply_forwarded_headers(url: str, request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")

    if not forwarded_proto and not forwarded_host:
        return url

    parsed = urlsplit(url)
    scheme = forwarded_proto or parsed.scheme
    netloc = forwarded_host or parsed.netloc
    return urlunsplit((scheme, netloc, parsed.path, parsed.query, parsed.fragment))


