"""Polite HTTP client: declared User-Agent, request pacing, retries with exponential backoff."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ingestion.common.config import Settings

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    """Raised for status codes where a retry may succeed."""


class PoliteSession:
    """A requests session that never exceeds the configured request rate."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": settings.user_agent, "Accept-Encoding": "gzip, deflate"})
        self._lock = threading.Lock()
        self._last_request = 0.0

    def _pace(self) -> None:
        with self._lock:
            wait = self.settings.min_seconds_between_requests - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    @retry(
        retry=retry_if_exception_type((RetryableHTTPError, requests.ConnectionError, requests.Timeout)),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get(self, url: str, **kwargs) -> requests.Response:
        self._pace()
        response = self._session.get(url, timeout=kwargs.pop("timeout", 120), **kwargs)
        if response.status_code in RETRYABLE_STATUS:
            raise RetryableHTTPError(f"{response.status_code} for {url}")
        response.raise_for_status()
        return response

    def download(self, url: str, target: Path) -> tuple[str, int]:
        """Stream a file to disk. Returns (sha256, bytes). Writes atomically via a temp file."""
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        size = 0
        with self.get(url, stream=True) as response, tmp.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        tmp.replace(target)
        return digest.hexdigest(), size


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
