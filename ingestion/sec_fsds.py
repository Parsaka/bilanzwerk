"""SEC Financial Statement Data Sets loader.

One zip per quarter (2009q2 onwards) with four tab-separated files: sub, num, tag, pre.
Contract: download, verify, land as Parquet under raw/sec_fsds/<table>/quarter=<yyyyqn>/,
write a manifest row per table. Running twice changes nothing.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from ingestion.common.config import Settings
from ingestion.common.http import PoliteSession, sha256_file
from ingestion.common.manifest import STATUS_FAILED, STATUS_LOADED, Manifest, ManifestRow
from ingestion.common.parquet import write_partition

log = logging.getLogger(__name__)

SOURCE = "sec_fsds"
BASE_URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{quarter}.zip"
FIRST_QUARTER = (2009, 2)

TEXT = pa.string()
VALUE = pa.decimal128(38, 6)

# Explicit column types. Columns not listed are kept as text. "required" columns form the
# data contract: if the SEC renames one, the load fails loudly instead of landing nulls.
SCHEMAS: dict[str, dict[str, pa.DataType]] = {
    "sub": {
        "adsh": TEXT,
        "cik": pa.int64(),
        "name": TEXT,
        "sic": pa.int32(),
        "countryba": TEXT,
        "stprba": TEXT,
        "cityba": TEXT,
        "zipba": TEXT,
        "countryinc": TEXT,
        "former": TEXT,
        "changed": TEXT,
        "afs": TEXT,
        "fye": TEXT,
        "form": TEXT,
        "period": TEXT,
        "fy": pa.int32(),
        "fp": TEXT,
        "filed": TEXT,
        "accepted": TEXT,
        "prevrpt": pa.int8(),
        "detail": pa.int8(),
        "instance": TEXT,
        "nciks": pa.int32(),
        "aciks": TEXT,
    },
    "num": {
        "adsh": TEXT,
        "tag": TEXT,
        "version": TEXT,
        "ddate": TEXT,
        "qtrs": pa.int32(),
        "uom": TEXT,
        "segments": TEXT,
        "coreg": TEXT,
        "value": VALUE,
        "footnote": TEXT,
    },
    "tag": {
        "tag": TEXT,
        "version": TEXT,
        "custom": pa.int8(),
        "abstract": pa.int8(),
        "datatype": TEXT,
        "iord": TEXT,
        "crdr": TEXT,
        "tlabel": TEXT,
        "doc": TEXT,
    },
    "pre": {
        "adsh": TEXT,
        "report": pa.int32(),
        "line": pa.int32(),
        "stmt": TEXT,
        "inpth": pa.int8(),
        "rfile": TEXT,
        "tag": TEXT,
        "version": TEXT,
        "plabel": TEXT,
        "negating": pa.int8(),
    },
}

REQUIRED: dict[str, set[str]] = {
    "sub": {
        "adsh",
        "cik",
        "name",
        "sic",
        "countryba",
        "fye",
        "form",
        "period",
        "fy",
        "fp",
        "filed",
        "accepted",
        "prevrpt",
        "instance",
    },
    "num": {"adsh", "tag", "version", "ddate", "qtrs", "uom", "value"},
    "tag": {"tag", "version", "custom", "abstract", "datatype", "iord", "crdr", "tlabel"},
    "pre": {"adsh", "report", "line", "stmt", "inpth", "tag", "version", "plabel", "negating"},
}

# yyyymmdd text columns that become dates
DATE_COLUMNS = {"sub": ["period", "filed"], "num": ["ddate"]}


class ContractError(ValueError):
    """The file does not match the expected column contract."""


@dataclass(frozen=True)
class Quarter:
    year: int
    q: int

    @property
    def label(self) -> str:
        return f"{self.year}q{self.q}"

    @classmethod
    def parse(cls, label: str) -> Quarter:
        year, q = label.lower().split("q")
        return cls(int(year), int(q))


def list_quarters(start: Quarter | None = None, end: Quarter | None = None, today: date | None = None) -> list[Quarter]:
    """All quarters from start (default 2009q2) up to the last completed quarter."""
    today = today or date.today()
    start = start or Quarter(*FIRST_QUARTER)
    if end is None:
        current_q = (today.month - 1) // 3 + 1
        end = Quarter(today.year, current_q - 1) if current_q > 1 else Quarter(today.year - 1, 4)
    out = []
    y, q = start.year, start.q
    while (y, q) <= (end.year, end.q):
        out.append(Quarter(y, q))
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)
    return out


def read_table(raw: bytes, table: str) -> pa.Table:
    """Parse one tab-separated FSDS member with the explicit schema."""
    header = raw.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip("\r").split("\t")
    missing = REQUIRED[table] - set(header)
    if missing:
        raise ContractError(f"{table}.txt is missing required columns: {sorted(missing)}")

    schema = SCHEMAS[table]
    # Read everything as text first, then cast: SEC files contain values like "" in int columns.
    tbl = pacsv.read_csv(
        io.BytesIO(raw),
        read_options=pacsv.ReadOptions(encoding="utf-8", block_size=1 << 26),
        parse_options=pacsv.ParseOptions(delimiter="\t", quote_char=False, newlines_in_values=False),
        convert_options=pacsv.ConvertOptions(
            column_types={c: pa.string() for c in header},
            strings_can_be_null=True,
            null_values=[""],
        ),
    )
    columns = {}
    for name in header:
        col = tbl.column(name)
        target = schema.get(name, TEXT)
        if name in DATE_COLUMNS.get(table, []):
            columns[name] = pc.strptime(col, format="%Y%m%d", unit="s", error_is_null=True).cast(pa.date32())
        elif name == "accepted":
            columns[name] = pc.strptime(
                pc.utf8_slice_codeunits(col, 0, 19), format="%Y-%m-%d %H:%M:%S", unit="s", error_is_null=True
            )
        elif target != TEXT:
            columns[name] = col.cast(target)
        else:
            columns[name] = col
    # Columns from the schema that this vintage of the file does not have (e.g. segments
    # before 2024) are added as nulls so every quarter has the same shape.
    for name, typ in schema.items():
        if name not in columns:
            columns[name] = pa.nulls(tbl.num_rows, type=pa.date32() if name in DATE_COLUMNS.get(table, []) else typ)
    return pa.table(columns)


def verify_zip(path: Path) -> zipfile.ZipFile:
    """Open the zip and check every member's CRC. A broken zip fails loudly."""
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise zipfile.BadZipFile(f"{path.name} is not a valid zip: {exc}") from exc
    bad = zf.testzip()
    if bad is not None:
        raise zipfile.BadZipFile(f"{path.name}: member {bad} failed CRC check")
    names = {n.lower() for n in zf.namelist()}
    for t in SCHEMAS:
        if f"{t}.txt" not in names:
            raise ContractError(f"{path.name} has no {t}.txt")
    return zf


def land_zip(
    path: Path, quarter: Quarter, settings: Settings, manifest: Manifest, url: str | None = None
) -> dict[str, int]:
    """Land one already-downloaded quarter zip. Skips it if the checksum is already loaded."""
    digest = sha256_file(path)
    if manifest.is_loaded(SOURCE, digest):
        log.info("%s already loaded (checksum match), skipping", path.name)
        return {}
    counts: dict[str, int] = {}
    try:
        zf = verify_zip(path)
        members = {n.lower(): n for n in zf.namelist()}
        for table in SCHEMAS:
            tbl = read_table(zf.read(members[f"{table}.txt"]), table)
            write_partition(tbl, settings.raw_root / SOURCE / table, {"quarter": quarter.label})
            counts[table] = tbl.num_rows
    except Exception as exc:
        manifest.record(
            ManifestRow(
                SOURCE,
                path.name,
                quarter.label,
                url,
                digest,
                path.stat().st_size,
                None,
                None,
                STATUS_FAILED,
                str(exc)[:1000],
            )
        )
        raise
    for table, n in counts.items():
        manifest.record(
            ManifestRow(SOURCE, path.name, quarter.label, url, digest, path.stat().st_size, n, table, STATUS_LOADED)
        )
    log.info("%s landed: %s", quarter.label, counts)
    return counts


def run(settings: Settings, quarters: list[Quarter], session: PoliteSession | None = None) -> dict[str, dict[str, int]]:
    session = session or PoliteSession(settings)
    manifest = Manifest(settings.manifest_path)
    results = {}
    for quarter in quarters:
        url = BASE_URL.format(quarter=quarter.label)
        target = settings.download_root / SOURCE / f"{quarter.label}.zip"
        if not target.exists():
            log.info("downloading %s", url)
            session.download(url, target)
        results[quarter.label] = land_zip(target, quarter, settings, manifest, url)
    return results
