"""ESEF (European IFRS annual reports) loader from filings.xbrl.org.

Pages through the JSON:API at /api/filings for target countries, downloads each filing's
xBRL-JSON, and flattens facts to (lei, concept, period, unit, value, decimals). Only facts
without extra dimensions are kept (company totals).

Output: raw/esef/filings/country=XX/ and raw/esef/facts/country=XX/filing=<fxo_id>/
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pyarrow as pa

from ingestion.common.config import Settings
from ingestion.common.http import PoliteSession
from ingestion.common.manifest import STATUS_LOADED, Manifest, ManifestRow
from ingestion.common.parquet import write_partition

log = logging.getLogger(__name__)

SOURCE = "esef"
BASE = "https://filings.xbrl.org"
API = BASE + "/api/filings"
DEFAULT_COUNTRIES = ["DE", "AT", "NL", "FR", "IT", "ES", "BE", "FI", "IE", "DK", "SE", "PL"]

SIX_PLACES = Decimal("0.000001")
CORE_DIMENSIONS = {"concept", "entity", "period", "unit", "language"}

FACT_SCHEMA = pa.schema(
    [
        ("fxo_id", pa.string()),
        ("lei", pa.string()),
        ("concept", pa.string()),
        ("period_start", pa.date32()),
        ("period_end", pa.date32()),
        ("is_instant", pa.bool_()),
        ("unit", pa.string()),
        ("value", pa.decimal128(38, 6)),
        ("decimals", pa.int32()),
    ]
)
FILING_SCHEMA = pa.schema(
    [
        ("fxo_id", pa.string()),
        ("lei", pa.string()),
        ("entity_name", pa.string()),
        ("country", pa.string()),
        ("period_end", pa.date32()),
        ("date_added", pa.string()),
        ("json_url", pa.string()),
        ("error_count", pa.int32()),
    ]
)


def _xbrl_date(value: str, is_end: bool) -> date:
    """xBRL-JSON uses exclusive midnight ends: '2022-01-01T00:00:00' means end of 2021-12-31."""
    if "T" not in value:
        return date.fromisoformat(value)
    dt = datetime.fromisoformat(value)
    if is_end and dt.time() == datetime.min.time():
        return (dt - timedelta(days=1)).date()
    return dt.date()


def parse_period(period: str) -> tuple[date | None, date, bool]:
    if "/" in period:
        start, end = period.split("/")
        return _xbrl_date(start, False), _xbrl_date(end, True), False
    return None, _xbrl_date(period, True), True


def flatten_facts(fxo_id: str, doc: dict) -> Iterator[dict]:
    for fact in (doc.get("facts") or {}).values():
        dims = fact.get("dimensions") or {}
        if set(dims) - CORE_DIMENSIONS:
            continue  # dimensional (segment) fact, not a company total
        unit = dims.get("unit")
        value = fact.get("value")
        if unit is None or value is None:
            continue  # text or nil facts
        try:
            numeric = Decimal(str(value)).quantize(SIX_PLACES)
        except (InvalidOperation, ValueError):
            continue
        start, end, instant = parse_period(dims["period"])
        decimals = fact.get("decimals")
        yield {
            "fxo_id": fxo_id,
            "lei": (dims.get("entity") or "").split(":")[-1] or None,
            "concept": dims["concept"],
            "period_start": start,
            "period_end": end,
            "is_instant": instant,
            "unit": unit,
            "value": numeric,
            "decimals": None if decimals in (None, "INF") else int(decimals),
        }


def iter_filings(session: PoliteSession, country: str, page_size: int = 200) -> Iterator[dict]:
    page = 1
    while True:
        params = {
            "filter": json.dumps([{"name": "country", "op": "eq", "val": country}]),
            "include": "entity",
            "page[size]": page_size,
            "page[number]": page,
        }
        payload = session.get(API, params=params).json()
        entities = {e["id"]: e.get("attributes", {}) for e in payload.get("included", []) if e.get("type") == "entity"}
        for item in payload.get("data", []):
            attrs = item.get("attributes", {})
            ent_id = ((item.get("relationships") or {}).get("entity") or {}).get("data", {}) or {}
            ent = entities.get(ent_id.get("id"), {})
            yield {
                "fxo_id": attrs.get("fxo_id") or item.get("id"),
                "lei": ent.get("identifier"),
                "entity_name": ent.get("name"),
                "country": attrs.get("country", country),
                "period_end": date.fromisoformat(attrs["period_end"]) if attrs.get("period_end") else None,
                "date_added": attrs.get("date_added"),
                "json_url": attrs.get("json_url"),
                "error_count": attrs.get("error_count"),
            }
        if not (payload.get("links") or {}).get("next"):
            return
        page += 1


def run(
    settings: Settings, countries: list[str] | None = None, min_year: int = 2020, session: PoliteSession | None = None
) -> dict[str, int]:
    session = session or PoliteSession(settings)
    manifest = Manifest(settings.manifest_path)
    done = manifest.loaded_files(SOURCE)
    out = {}
    for country in countries or DEFAULT_COUNTRIES:
        filings = [
            f
            for f in iter_filings(session, country)
            if f["json_url"] and f["period_end"] and f["period_end"].year >= min_year
        ]
        write_partition(
            pa.Table.from_pylist(filings, schema=FILING_SCHEMA),
            settings.raw_root / SOURCE / "filings",
            {"country": country},
        )
        n_facts = 0
        for f in filings:
            name = f"{f['fxo_id']}.json"
            if name in done:
                continue
            response = session.get(BASE + f["json_url"])
            rows = list(flatten_facts(f["fxo_id"], response.json()))
            tbl = pa.Table.from_pylist(rows, schema=FACT_SCHEMA)
            write_partition(tbl, settings.raw_root / SOURCE / "facts", {"country": country, "filing": f["fxo_id"]})
            manifest.record(
                ManifestRow(
                    SOURCE,
                    name,
                    str(f["period_end"]),
                    BASE + f["json_url"],
                    hashlib.sha256(response.content).hexdigest(),
                    len(response.content),
                    tbl.num_rows,
                    "facts",
                    STATUS_LOADED,
                )
            )
            n_facts += tbl.num_rows
        out[country] = n_facts
    return out
