"""SEC submissions bulk loader (submissions.zip, one JSON per company, republished nightly).

Used for the event label (8-K Item 1.03), Form 15/25 for the distress label, NT 10-K late
filings, and the company name history (SCD Type 2). Output, partitioned by load date:

    raw/sec_submissions/companies/load_date=YYYY-MM-DD/
    raw/sec_submissions/former_names/load_date=YYYY-MM-DD/
    raw/sec_submissions/filings/load_date=YYYY-MM-DD/
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

import pyarrow as pa

from ingestion.common.config import Settings
from ingestion.common.http import PoliteSession, sha256_file
from ingestion.common.manifest import STATUS_FAILED, STATUS_LOADED, Manifest, ManifestRow
from ingestion.common.parquet import write_partition

log = logging.getLogger(__name__)

SOURCE = "sec_submissions"
URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"

# Only the forms the analysis and the history need. Prefix match, so "8-K" also keeps "8-K/A".
FORMS_OF_INTEREST = (
    "8-K",
    "10-K",
    "10-Q",
    "20-F",
    "40-F",
    "15-12",
    "15-15",
    "15F",
    "15",
    "25",
    "NT 10-K",
    "NT 10-Q",
    "NT 20-F",
)

MEMBER_RE = re.compile(r"CIK(\d{10})(?:-submissions-\d+)?\.json$")

COMPANY_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("name", pa.string()),
        ("entity_type", pa.string()),
        ("sic", pa.int32()),
        ("sic_description", pa.string()),
        ("tickers", pa.list_(pa.string())),
        ("exchanges", pa.list_(pa.string())),
        ("fiscal_year_end", pa.string()),
        ("state_of_incorporation", pa.string()),
        ("business_city", pa.string()),
        ("business_state", pa.string()),
        ("business_zip", pa.string()),
        ("lei", pa.string()),
    ]
)
FORMER_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("name", pa.string()),
        ("valid_from", pa.string()),
        ("valid_to", pa.string()),
    ]
)
FILING_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("accession_number", pa.string()),
        ("form", pa.string()),
        ("filing_date", pa.date32()),
        ("report_date", pa.date32()),
        ("acceptance_datetime", pa.string()),
        ("items", pa.string()),
    ]
)


def keep_form(form: str | None) -> bool:
    if not form:
        return False
    return any(form == f or form.startswith(f + "/") or form.startswith(f + "-") for f in FORMS_OF_INTEREST)


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def flatten_filings(cik: int, block: dict) -> Iterator[dict]:
    """Turn the column-oriented filings arrays into rows."""
    accession = block.get("accessionNumber", [])
    n = len(accession)

    def col(name: str) -> list:
        values = block.get(name) or [None] * n
        return values if len(values) == n else [None] * n

    forms, filed, report, accepted, items = (
        col("form"),
        col("filingDate"),
        col("reportDate"),
        col("acceptanceDateTime"),
        col("items"),
    )
    for i in range(n):
        if keep_form(forms[i]):
            yield {
                "cik": cik,
                "accession_number": accession[i],
                "form": forms[i],
                "filing_date": _date(filed[i]),
                "report_date": _date(report[i]),
                "acceptance_datetime": accepted[i],
                "items": items[i] or None,
            }


def parse_member(name: str, payload: dict) -> tuple[dict | None, list[dict], list[dict]]:
    """Returns (company row or None, former name rows, filing rows) for one JSON member."""
    m = MEMBER_RE.search(name)
    if not m:
        return None, [], []
    cik = int(m.group(1))
    if "filings" not in payload:  # an overflow page: arrays at the top level
        return None, [], list(flatten_filings(cik, payload))
    address = (payload.get("addresses") or {}).get("business") or {}
    sic = payload.get("sic")
    company = {
        "cik": cik,
        "name": payload.get("name"),
        "entity_type": payload.get("entityType"),
        "sic": int(sic) if sic not in (None, "") else None,
        "sic_description": payload.get("sicDescription"),
        "tickers": payload.get("tickers") or [],
        "exchanges": [e for e in payload.get("exchanges") or [] if e],
        "fiscal_year_end": payload.get("fiscalYearEnd"),
        "state_of_incorporation": payload.get("stateOfIncorporation"),
        "business_city": address.get("city"),
        "business_state": address.get("stateOrCountry"),
        "business_zip": address.get("zipCode"),
        "lei": payload.get("lei"),
    }
    former = [
        {"cik": cik, "name": f.get("name"), "valid_from": f.get("from"), "valid_to": f.get("to")}
        for f in payload.get("formerNames") or []
    ]
    filings = list(flatten_filings(cik, (payload.get("filings") or {}).get("recent") or {}))
    return company, former, filings


def iter_zip(path: Path) -> Iterable[tuple[str, dict]]:
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.filename.endswith(".json"):
                with zf.open(info) as fh:
                    yield info.filename, json.load(fh)


def land_zip(
    path: Path,
    load_date: date,
    settings: Settings,
    manifest: Manifest,
    url: str | None = None,
    batch_size: int = 50_000,
) -> dict[str, int]:
    digest = sha256_file(path)
    if manifest.is_loaded(SOURCE, digest):
        log.info("%s already loaded, skipping", path.name)
        return {}
    root = settings.raw_root / SOURCE
    part = {"load_date": load_date.isoformat()}
    counts = {"companies": 0, "former_names": 0, "filings": 0}
    buffers: dict[str, list[dict]] = {k: [] for k in counts}
    schemas = {"companies": COMPANY_SCHEMA, "former_names": FORMER_SCHEMA, "filings": FILING_SCHEMA}
    part_no = {k: 0 for k in counts}

    def flush(key: str, force: bool = False) -> None:
        if buffers[key] and (force or len(buffers[key]) >= batch_size):
            write_partition(
                pa.Table.from_pylist(buffers[key], schema=schemas[key]),
                root / key,
                part,
                name=f"part-{part_no[key]:05d}",
            )
            counts[key] += len(buffers[key])
            part_no[key] += 1
            buffers[key] = []

    try:
        for name, payload in iter_zip(path):
            company, former, filings = parse_member(name, payload)
            if company:
                buffers["companies"].append(company)
            buffers["former_names"].extend(former)
            buffers["filings"].extend(filings)
            for key in counts:
                flush(key)
        for key in counts:
            flush(key, force=True)
    except Exception as exc:
        manifest.record(
            ManifestRow(
                SOURCE,
                path.name,
                load_date.isoformat(),
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
    for key, n in counts.items():
        manifest.record(
            ManifestRow(
                SOURCE, path.name, load_date.isoformat(), url, digest, path.stat().st_size, n, key, STATUS_LOADED
            )
        )
    return counts


def run(settings: Settings, load_date: date | None = None, session: PoliteSession | None = None) -> dict[str, int]:
    load_date = load_date or date.today()
    session = session or PoliteSession(settings)
    target = settings.download_root / SOURCE / f"submissions_{load_date.isoformat()}.zip"
    if not target.exists():
        session.download(URL, target)
    return land_zip(target, load_date, settings, Manifest(settings.manifest_path), URL)
