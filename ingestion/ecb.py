"""ECB euro reference rates (dataset EXR, daily, since 1999) from the ECB Data Portal API.

Rates are quoted as units of foreign currency per 1 EUR. Every run fetches from the day after
the last landed date and appends a partition fetch_date=YYYY-MM-DD; staging deduplicates on
(currency, rate_date) so overlapping fetches are harmless.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import date, timedelta
from decimal import Decimal

import pyarrow as pa
import pyarrow.dataset as ds

from ingestion.common.config import Settings
from ingestion.common.http import PoliteSession
from ingestion.common.manifest import STATUS_LOADED, Manifest, ManifestRow
from ingestion.common.parquet import write_partition

log = logging.getLogger(__name__)

SOURCE = "ecb"
URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A"
FIRST_DATE = date(1999, 1, 4)

# All currencies with an ECB reference rate today plus discontinued ones that appear in old filings.
DEFAULT_CURRENCIES = [
    "USD",
    "JPY",
    "BGN",
    "CZK",
    "DKK",
    "GBP",
    "HUF",
    "PLN",
    "RON",
    "SEK",
    "CHF",
    "ISK",
    "NOK",
    "TRY",
    "AUD",
    "BRL",
    "CAD",
    "CNY",
    "HKD",
    "IDR",
    "ILS",
    "INR",
    "KRW",
    "MXN",
    "MYR",
    "NZD",
    "PHP",
    "SGD",
    "THB",
    "ZAR",
    "RUB",
    "HRK",
    "LTL",
    "LVL",
    "EEK",
    "SKK",
    "CYP",
    "MTL",
]

SCHEMA = pa.schema(
    [
        ("currency", pa.string()),
        ("rate_date", pa.date32()),
        ("rate_per_eur", pa.decimal128(18, 6)),
    ]
)


def parse_csv(text: str) -> pa.Table:
    currencies, dates, values = [], [], []
    for rec in csv.DictReader(io.StringIO(text)):
        value = rec.get("OBS_VALUE")
        if not value or value == "NaN":
            continue
        currencies.append(rec["CURRENCY"])
        dates.append(date.fromisoformat(rec["TIME_PERIOD"]))
        values.append(Decimal(value))
    return pa.table(
        {"currency": currencies, "rate_date": dates, "rate_per_eur": pa.array(values, type=pa.decimal128(18, 6))},
        schema=SCHEMA,
    )


def last_loaded_date(settings: Settings) -> date | None:
    root = settings.raw_root / SOURCE / "rates"
    if not root.exists():
        return None
    tbl = ds.dataset(root, format="parquet", partitioning="hive").to_table(columns=["rate_date"])
    if tbl.num_rows == 0:
        return None
    return max(tbl.column("rate_date").to_pylist())


def run(
    settings: Settings,
    currencies: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    session: PoliteSession | None = None,
) -> int:
    currencies = currencies or DEFAULT_CURRENCIES
    session = session or PoliteSession(settings)
    last = last_loaded_date(settings)
    start = start or ((last + timedelta(days=1)) if last else FIRST_DATE)
    end = end or date.today()
    if start > end:
        log.info("ECB rates up to date (%s)", last)
        return 0
    url = URL.format(currencies="+".join(sorted(currencies)))
    params = {"format": "csvdata", "startPeriod": start.isoformat(), "endPeriod": end.isoformat()}
    response = session.get(url, params=params, headers={"Accept": "text/csv"})
    if response.status_code == 404 or not response.text.strip():
        return 0  # no new observations (weekend, holiday)
    tbl = parse_csv(response.text)
    digest = hashlib.sha256(response.content).hexdigest()
    manifest = Manifest(settings.manifest_path)
    if manifest.is_loaded(SOURCE, digest):
        return 0
    fetch = date.today().isoformat()
    write_partition(
        tbl, settings.raw_root / SOURCE / "rates", {"fetch_date": fetch}, name=f"{start.isoformat()}_{end.isoformat()}"
    )
    manifest.record(
        ManifestRow(
            SOURCE,
            f"exr_{start}_{end}.csv",
            f"{start}..{end}",
            response.url,
            digest,
            len(response.content),
            tbl.num_rows,
            "rates",
            STATUS_LOADED,
        )
    )
    return tbl.num_rows
