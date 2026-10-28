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


def next_quarter(quarter: Quarter) -> Quarter:
    return Quarter(quarter.year, quarter.q + 1) if quarter.q < 4 else Quarter(quarter.year + 1, 1)


def newly_published(after: Quarter, session: PoliteSession, today: date | None = None) -> list[Quarter]:
    """Completed quarters after `after` whose zip the SEC has published (HEAD 200), oldest first.

    Used by the quarterly workflow to start a load only when there is something new; it stops at
    the first quarter that is not there yet.
    """
    out = []
    for quarter in list_quarters(next_quarter(after), today=today):
        response = session.head(BASE_URL.format(quarter=quarter.label))
        if response.status_code != 200:
            break
        out.append(quarter)
    return out


# Renamed columns the loader accepts, per table: {name in the file: name in the contract}.
# Empty on purpose. An entry is added only after a contract break was triaged as a pure rename
# (same meaning, same values), together with a test; see docs/incident-drill.md.
COLUMN_ALIASES: dict[str, dict[str, str]] = {table: {} for table in ("sub", "num", "tag", "pre")}


def _parse_tsv(raw: bytes, header: list[str], quoted: bool) -> pa.Table:
    # Read everything as text first, then cast: SEC files contain values like "" in int columns.
    return pacsv.read_csv(
        io.BytesIO(raw),
        read_options=pacsv.ReadOptions(encoding="utf-8", block_size=1 << 26),
        parse_options=pacsv.ParseOptions(
            delimiter="\t", quote_char='"' if quoted else False, double_quote=quoted, newlines_in_values=quoted
        ),
        convert_options=pacsv.ConvertOptions(
            column_types={c: pa.string() for c in header},
            strings_can_be_null=True,
            null_values=[""],
        ),
    )


def read_table(raw: bytes, table: str) -> pa.Table:
    """Parse one tab-separated FSDS member with the explicit schema."""
    header = raw.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip("\r").split("\t")
    aliases = COLUMN_ALIASES.get(table, {})
    missing = REQUIRED[table] - {aliases.get(c, c) for c in header}
    if missing:
        raise ContractError(f"{table}.txt is missing required columns: {sorted(missing)}")

    schema = SCHEMAS[table]
    try:
        # Most files: no quoting, so a stray " inside a label stays part of the value.
        tbl = _parse_tsv(raw, header, quoted=False)
    except pa.ArrowInvalid:
        # Some quarters (e.g. 2022q4 num.txt) wrap values that contain tabs or line breaks in
        # double quotes; parse those files with CSV quoting.
        log.info("%s.txt has quoted values with tabs or line breaks; parsing with quoting", table)
        tbl = _parse_tsv(raw, header, quoted=True)
    columns = {}
    for file_name in header:
        col = tbl.column(file_name)
        name = aliases.get(file_name, file_name)
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
        # Parse and check every table before writing any: a contract break in num.txt must not
        # leave a new sub partition next to the old num partition of the same quarter.
        tables = {table: read_table(zf.read(members[f"{table}.txt"]), table) for table in SCHEMAS}
        for table, tbl in tables.items():
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


def run(
    settings: Settings,
    quarters: list[Quarter],
    session: PoliteSession | None = None,
    recheck: bool = False,
) -> dict[str, dict[str, int]]:
    """Download and land the given quarters.

    Quarters already in the manifest are not downloaded again (the archives are deleted after
    landing on the runners; 70+ zips of several GB each would otherwise be fetched on every run).
    `recheck` downloads them anyway, so a republished zip is found by its new checksum. The last
    quarter is skipped with a warning while the SEC has not published it yet.
    """
    session = session or PoliteSession(settings)
    manifest = Manifest(settings.manifest_path)
    loaded = set() if recheck else manifest.loaded_files(SOURCE)
    results: dict[str, dict[str, int]] = {}
    for quarter in quarters:
        url = BASE_URL.format(quarter=quarter.label)
        target = settings.download_root / SOURCE / f"{quarter.label}.zip"
        if target.name in loaded:
            log.info("%s already loaded, not downloaded again", quarter.label)
            results[quarter.label] = {}
            continue
        if not target.exists():
            if quarter == quarters[-1] and session.head(url).status_code == 404:
                log.warning("%s is not published yet, skipped", quarter.label)
                break
            log.info("downloading %s", url)
            session.download(url, target)
        results[quarter.label] = land_zip(target, quarter, settings, manifest, url)
    return results
