"""The ingest manifest: one row per landed file. A loader skips a file whose checksum is loaded.

Locally the manifest is a DuckDB table; in Fabric the same rows are written to a Lakehouse
Delta table by the pipeline (see fabric/). The contract is the column list below.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

DDL = """
create table if not exists ingest_manifest (
    source        varchar   not null,
    file_name     varchar   not null,
    period        varchar,
    url           varchar,
    sha256        varchar   not null,
    bytes         bigint,
    rows          bigint,
    table_name    varchar,
    downloaded_at timestamp not null,
    status        varchar   not null,
    message       varchar
)
"""

STATUS_LOADED = "loaded"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class ManifestRow:
    source: str
    file_name: str
    period: str | None
    url: str | None
    sha256: str
    bytes: int | None
    rows: int | None
    table_name: str | None
    status: str
    message: str | None = None


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(DDL)

    @contextmanager
    def _connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        con = duckdb.connect(str(self.path))
        try:
            yield con
        finally:
            con.close()

    def is_loaded(self, source: str, sha256: str) -> bool:
        with self._connect() as con:
            hit = con.execute(
                "select count(*) from ingest_manifest where source = ? and sha256 = ? and status = ?",
                [source, sha256, STATUS_LOADED],
            ).fetchone()
        return bool(hit and hit[0])

    def loaded_files(self, source: str) -> set[str]:
        with self._connect() as con:
            rows = con.execute(
                "select distinct file_name from ingest_manifest where source = ? and status = ?",
                [source, STATUS_LOADED],
            ).fetchall()
        return {r[0] for r in rows}

    def record(self, row: ManifestRow) -> None:
        with self._connect() as con:
            con.execute(
                "insert into ingest_manifest values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    row.source,
                    row.file_name,
                    row.period,
                    row.url,
                    row.sha256,
                    row.bytes,
                    row.rows,
                    row.table_name,
                    datetime.now(UTC).replace(tzinfo=None),
                    row.status,
                    row.message,
                ],
            )

    def rows(self, source: str | None = None) -> list[tuple]:
        with self._connect() as con:
            if source:
                return con.execute(
                    "select * from ingest_manifest where source = ? order by downloaded_at", [source]
                ).fetchall()
            return con.execute("select * from ingest_manifest order by downloaded_at").fetchall()
