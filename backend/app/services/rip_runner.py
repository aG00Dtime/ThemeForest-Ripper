from __future__ import annotations

import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..core.config import Settings
from .job_store import JobStore


class JobCancelled(Exception):
    """Raised when a job cancellation is requested."""


class RipRunner:
    """Encapsulates the Selenium + wget workflow for a single job."""

    def __init__(self, settings: Settings, store: JobStore) -> None:
        self._settings = settings
        self._store = store

    def run(self, job_id: str, theme_url: str) -> None:
        storage_dir = self._settings.jobs_root / job_id
        mirror_dir = storage_dir / "mirror"

        try:
            self._ensure_not_cancelled(job_id)
            self._store.mark_running(job_id)
            self._ensure_not_cancelled(job_id)
            self._store.append_log(job_id, "info", "Job accepted, starting extraction")

            mirror_dir.mkdir(parents=True, exist_ok=True)

            if "full_screen_preview" in theme_url:
                preview_url = theme_url
                self._store.append_log(job_id, "info", "Input URL already points to preview; skipping lookup")
            else:
                self._ensure_not_cancelled(job_id)
                preview_url = self._with_driver(
                    "Resolve preview URL", job_id, lambda driver: self._get_preview_url(driver, theme_url)
                )
                self._store.append_log(job_id, "info", f"Resolved preview URL {preview_url}")

            self._ensure_not_cancelled(job_id)
            full_frame_url = self._with_driver("Resolve full frame URL", job_id, lambda driver: self._get_full_frame_url(driver, preview_url))
            self._store.append_log(job_id, "info", f"Resolved frame URL {full_frame_url}")

            self._ensure_not_cancelled(job_id)
            self._mirror_site(job_id, full_frame_url, mirror_dir)
            self._ensure_not_cancelled(job_id)

            zip_path = self._create_archive(storage_dir, mirror_dir, job_id)
            self._store.append_log(job_id, "info", f"Created archive {zip_path.name}")
            with suppress(Exception):
                shutil.rmtree(mirror_dir, ignore_errors=True)

            self._store.mark_succeeded(job_id, zip_path)
            self._store.append_log(job_id, "info", "Job completed successfully")
        except JobCancelled:
            self._store.append_log(job_id, "info", "Job cancelled by user")
            self._store.mark_cancelled(job_id)
            with suppress(Exception):
                shutil.rmtree(storage_dir, ignore_errors=True)
            self._store.remove(job_id)
        except Exception as exc:  # noqa: BLE001 - surface all errors to client
            self._store.append_log(job_id, "error", str(exc))
            self._store.mark_failed(job_id, str(exc))
            with suppress(Exception):
                shutil.rmtree(storage_dir, ignore_errors=True)
            raise

    def _with_driver(self, description: str, job_id: str, func: Callable[[webdriver.Chrome], str]) -> str:
        driver = self._build_driver(job_id)
        try:
            self._store.append_log(job_id, "info", f"{description}")
            self._ensure_not_cancelled(job_id)
            return func(driver)
        except WebDriverException as exc:
            raise RuntimeError(f"{description} failed: {exc.msg}") from exc
        finally:
            driver.quit()

    def _build_driver(self, job_id: str) -> webdriver.Chrome:
        options = ChromeOptions()
        if self._settings.chrome_binary_path:
            chrome_path = Path(self._settings.chrome_binary_path)
            if chrome_path.exists():
                options.binary_location = str(chrome_path)
            else:
                self._store.append_log(
                    job_id,
                    "warn",
                    f"Chrome binary not found at {chrome_path}, falling back to default lookup",
                )
        if self._settings.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        service: ChromeService | None = None
        if self._settings.chromedriver_path:
            driver_path = Path(self._settings.chromedriver_path)
            if driver_path.exists():
                service = ChromeService(executable_path=str(driver_path))
            else:
                self._store.append_log(
                    job_id,
                    "warn",
                    f"Chromedriver binary not found at {driver_path}, falling back to default lookup",
                )

        if service is None:
            return webdriver.Chrome(options=options)
        return webdriver.Chrome(service=service, options=options)

    def _get_preview_url(self, driver: webdriver.Chrome, item_url: str) -> str:
        driver.get(item_url)
        WebDriverWait(driver, 30).until(lambda d: "Just a moment" not in d.title)
        preview_link = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="full_screen_preview"]'))
        )
        return preview_link.get_attribute("href")

    def _get_full_frame_url(self, driver: webdriver.Chrome, preview_url: str) -> str:
        driver.get(preview_url)
        WebDriverWait(driver, 30).until(lambda d: "Just a moment" not in d.title)
        frame = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.full-screen-preview__frame"))
        )
        return frame.get_attribute("src")

    def _mirror_site(self, job_id: str, full_frame_url: str, dest_dir: Path) -> None:
        command = [
            "wget",
            "-e",
            "robots=off",
            "-P",
            str(dest_dir),
            "-m",
            full_frame_url,
        ]
        self._store.append_log(job_id, "info", f"Running {' '.join(command[:5])} ...")
        try:
            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            ) as process:
                assert process.stdout is not None
                last_url: str | None = None
                for line in process.stdout:
                    if self._store.is_cancelled(job_id):
                        process.terminate()
                        with suppress(subprocess.TimeoutExpired):
                            process.wait(timeout=5)
                        raise JobCancelled
                    entries, last_url = self._simplify_wget_line(line, last_url)
                    for level, message in entries:
                        self._store.append_log(job_id, level, message)
                retcode = process.wait()
                if self._store.is_cancelled(job_id):
                    raise JobCancelled
                if retcode == 8:
                    self._store.append_log(
                        job_id,
                        "warn",
                        "wget completed with HTTP errors (some assets may be missing)",
                    )
                elif retcode != 0:
                    raise RuntimeError(f"wget exited with code {retcode}")
        except FileNotFoundError as exc:
            raise RuntimeError("wget is required but not installed or not in PATH") from exc

    def _ensure_not_cancelled(self, job_id: str) -> None:
        if self._store.is_cancelled(job_id):
            raise JobCancelled

    def _create_archive(self, storage_dir: Path, source_dir: Path, job_id: str) -> Path:
        archive_path = storage_dir / f"{job_id}.zip"
        if archive_path.exists():
            archive_path.unlink()

        with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as zip_file:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zip_file.write(file_path, file_path.relative_to(source_dir))
        return archive_path

    def _simplify_wget_line(
        self,
        raw_line: str,
        last_url: str | None,
    ) -> tuple[list[tuple[str, str]], str | None]:
        line = raw_line.strip()
        if not line:
            return [], last_url

        uppercase = line.upper()
        if uppercase.startswith("ERROR"):
            return [("error", line)], last_url

        if line.startswith("--"):
            parts = line.split("--", 2)
            if len(parts) >= 3:
                url = parts[2].strip()
                if url:
                    label = self._resource_label(url)
                    return [("info", f"Fetching {label}")], url
            return [], last_url

        lowered = line.lower()
        if lowered.startswith("saving to:"):
            if last_url:
                label = self._resource_label(last_url)
                return [("info", f"Saved {label}")], last_url
            return [], last_url

        if "not retrieving" in lowered:
            return [("warn", line)], last_url

        return [], last_url

    @staticmethod
    def _resource_label(url: str) -> str:
        parsed = urlparse(url)
        name = Path(parsed.path).name
        if name:
            return name
        return parsed.netloc or url


