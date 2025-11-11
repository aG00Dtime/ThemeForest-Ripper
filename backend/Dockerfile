FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install --no-install-recommends -y \
    chromium \
    chromium-driver \
    wget \
    fonts-liberation \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /app/storage/jobs && chown -R app:app /app

USER app

ENV RIPPER_CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    RIPPER_CHROME_BINARY_PATH=/usr/bin/chromium \
    RIPPER_STORAGE_DIR=/app/storage \
    RIPPER_HEADLESS=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

