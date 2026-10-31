"""Runtime settings, read from environment variables so the same code runs locally and in Fabric."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # Root of the landing zone. Locally a folder, in Fabric the mounted Lakehouse "Files" path.
    data_root: Path = field(default_factory=lambda: Path(os.environ.get("BW_DATA_ROOT", "data")).resolve())
    # The SEC requires a declared User-Agent with a name and an e-mail address.
    user_agent: str = field(
        default_factory=lambda: os.environ.get("BW_USER_AGENT", "Bilanzwerk research contact@example.com")
    )
    # SEC fair-access rule: at most 10 requests per second. We stay well below.
    min_seconds_between_requests: float = field(
        default_factory=lambda: float(os.environ.get("BW_REQUEST_PAUSE", "0.5"))
    )

    @property
    def raw_root(self) -> Path:
        return self.data_root / "raw"

    @property
    def download_root(self) -> Path:
        return self.data_root / "downloads"

    @property
    def manifest_path(self) -> Path:
        return self.data_root / "_manifest" / "ingest_manifest.duckdb"


def get_settings() -> Settings:
    return Settings()
