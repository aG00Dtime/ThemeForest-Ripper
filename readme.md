# Theme Ripper

Modernized implementation of the original Selenium script, now exposed as an HTTP API with a React dashboard. Launch a rip job against any ThemeForest preview, watch live logs, and download the mirrored archive once the job completes.

- FastAPI backend with structured jobs/logging
- React + Vite control panel with live polling and auto-scroll logs
- Docker-first workflow (Chromium + chromedriver bundled)
- Artifacts stored under `storage/jobs/<job_id>.zip`
- Download links expire automatically (default 1 hour; configurable)
- Signed download tokens (SQLite-backed) keep internal API endpoints hidden

## Quick start (Docker)

```bash
docker compose up --build
```

Services:
- `proxy`: Nginx reverse proxy on `http://localhost:3000` routing `/v1` to the API
- `api`: FastAPI server (internal port 8000)
- `web`: Compiled React UI served behind the proxy

Job artifacts persist in the host `./storage` directory.

## Local development

### Backend (FastAPI)
```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Requirements:
- Python 3.11+
- Chromium + chromedriver on `PATH` (or set `RIPPER_CHROMEDRIVER_PATH`)
- `wget`

Key environment variables:
- `RIPPER_STORAGE_DIR` (default `storage/`)
- `RIPPER_MAX_WORKERS` (defaults to 2)
- `RIPPER_QUEUE_LIMIT` (defaults to 4)
- `RIPPER_JOB_TTL_SECONDS` (defaults to 3600) — retention window for completed jobs and their archives

API documentation lives in `docs/api.md`.

### Frontend (Vite + React)
```bash
cd frontend
npm install
npm run dev -- --host
```

By default the dev server proxies `/v1/*` requests to `http://localhost:8000`.
Configure a different backend by exporting `VITE_API_PROXY` or `VITE_API_BASE`.

### Running tests & checks

- Backend: `python -m compileall backend` (syntax), add pytest/ruff as needed.
- Frontend: `npm run build` (type-check + bundle).

## Architecture

- `backend/app/services/rip_runner.py` — wraps Selenium navigation + `wget`.
- `backend/app/services/job_store.py` — in-memory job metadata and log buffers.
- `backend/app/api/routes/rips.py` — `/v1/rips` endpoints for create/status/logs/download.
- `frontend/src/App.tsx` — single-page UI with form, status panel, and log viewer.

> The original README acknowledged there’s no foolproof way to prevent ThemeForest assets from being scraped—suggesting obfuscation, authenticated CDNs, or tracking as deterrents, while noting enforcement is difficult.

## Caveats

- This project rips publicly accessible previews; respect ThemeForest licensing.
- Use it for educational and archival purposes only—you’re responsible for complying with all contracts and laws.
- Container image includes Chromium/Chromedriver; keep them updated for security.
- Jobs are stored in memory; restart wipes the queue (artifacts stay on disk).

# Legacy script

The original `ripper.py` (CLI variant) remains in the repository for reference. It is no longer maintained now that the HTTP API supersedes it.
