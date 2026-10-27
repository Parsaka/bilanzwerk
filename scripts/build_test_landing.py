"""Build a small, synthetic landing zone for CI and local dbt tests.

TEST FIXTURE ONLY. Every number here is invented so that the pipeline can be exercised end
to end without network access. Nothing produced from this data is a result; results come only
from the real SEC, ESEF, GLEIF and ECB data (see docs/runbook.md).

The fixture runs the real loaders on generated source files, so the landed Parquet has
exactly the layout and types the production loaders write.

Usage: python scripts/build_test_landing.py --out .ci-data
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa

from ingestion import ecb, gleif, sec_fsds, sec_submissions
from ingestion.common.config import Settings
from ingestion.common.manifest import Manifest
from ingestion.common.parquet import write_partition


@dataclass
class Company:
    cik: int
    name: str
    sic: int
    fye_month: int
    lei: str | None
    revenue_q: float  # quarterly revenue at the start
    growth_q: float  # quarterly growth
    bankrupt_on: date | None = None


COMPANIES = [
    Company(1001, "ALPHA DEVICES INC", 3571, 12, "5493001KJTIIGC8Y1R12", 1_000e6, 0.02),
    Company(1002, "BETA RESTAURANTS CORP", 5812, 9, "5493002KJTIIGC8Y1R13", 400e6, 0.01),
    Company(1003, "GAMMA PHARMA INC", 2834, 12, None, 150e6, -0.08, bankrupt_on=date(2023, 9, 15)),
    Company(1004, "DELTA LOGISTICS INC", 4213, 12, None, 600e6, 0.015),
    Company(1005, "EPSILON SOFTWARE INC", 7372, 6, None, 300e6, 0.03),
    Company(1006, "ZETA RETAIL CORP", 5311, 1, None, 900e6, 0.0),
]
QUARTERS = [(y, q) for y in range(2020, 2024) for q in range(1, 5)]


def month_end(y: int, m: int) -> date:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return nxt - timedelta(days=1)


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return month_end(d.year + y, m + 1)


def fiscal_periods(c: Company) -> list[tuple[date, int]]:
    """(period_end, fiscal quarter) for the company's quarters inside the fixture window."""
    out = []
    end = month_end(2020, c.fye_month)
    while end > date(2020, 3, 31):
        end = add_months(end, -3)
    while end <= date(2023, 12, 31):
        fq = ((end.month - c.fye_month + 11) % 12) // 3 + 1
        if out or fq == 1:  # start at the first full fiscal year
            out.append((end, fq))
        end = add_months(end, 3)
    return out


def quarter_values(c: Company, i: int) -> dict[str, float]:
    """Synthetic single-quarter flows and period-end balances for quarter index i."""
    rev = c.revenue_q * (1 + c.growth_q) ** i
    cogs = rev * (0.62 if c.growth_q >= 0 else 0.78 + 0.02 * i)
    ebit = rev * (0.12 if c.growth_q >= 0 else -0.05 - 0.01 * i)
    da = rev * 0.04
    intexp = rev * (0.01 if c.growth_q >= 0 else 0.03)
    ni = (ebit - intexp) * 0.79
    ar_days = 45 + (0 if c.growth_q >= 0 else 4 * i)
    inv_days = 60 + (0 if c.growth_q >= 0 else 5 * i)
    ap_days = 50 - (0 if c.growth_q >= 0 else 1.5 * i)
    ar = rev * 4 * ar_days / 365
    inv = cogs * 4 * inv_days / 365
    ap = cogs * 4 * max(ap_days, 5) / 365
    cash = rev * (0.8 if c.growth_q >= 0 else max(0.6 - 0.04 * i, 0.02))
    ppe = rev * 3
    tca = cash + ar + inv
    ta = tca + ppe
    tcl = ap + rev * 0.2
    ltd = rev * (1.5 if c.growth_q >= 0 else 2.5)
    tl = tcl + ltd
    eq = ta - tl
    re = eq - rev * 0.5
    cfo = ni + da - (0 if c.growth_q >= 0 else rev * 0.05)
    return {
        "Revenues": rev, "CostOfRevenue": cogs, "OperatingIncomeLoss": ebit,
        "DepreciationDepletionAndAmortization": da, "InterestExpense": intexp, "NetIncomeLoss": ni,
        "NetCashProvidedByUsedInOperatingActivities": cfo,
        "CashAndCashEquivalentsAtCarryingValue": cash, "AccountsReceivableNetCurrent": ar,
        "InventoryNet": inv, "AssetsCurrent": tca, "PropertyPlantAndEquipmentNet": ppe, "Assets": ta,
        "AccountsPayableCurrent": ap, "LiabilitiesCurrent": tcl, "LongTermDebtNoncurrent": ltd,
        "Liabilities": tl, "StockholdersEquity": eq, "RetainedEarningsAccumulatedDeficit": re,
        "LiabilitiesAndStockholdersEquity": ta,
    }


FLOWS = {"Revenues", "CostOfRevenue", "OperatingIncomeLoss", "DepreciationDepletionAndAmortization",
         "InterestExpense", "NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities"}
YTD_ONLY = {"NetCashProvidedByUsedInOperatingActivities", "DepreciationDepletionAndAmortization"}


def build_fsds(out: Path) -> tuple[list[tuple], dict[int, list[tuple]]]:
    """Return per-quarter (sub rows, num rows) and filings per company for the submissions file."""
    per_quarter: dict[str, dict[str, list[str]]] = {}
    filings: dict[int, list[tuple]] = {c.cik: [] for c in COMPANIES}
    seq = 0
    for c in COMPANIES:
        periods = fiscal_periods(c)
        values = {end: quarter_values(c, i) for i, (end, _) in enumerate(periods)}
        for idx, (end, fq) in enumerate(periods):
            if c.bankrupt_on and end > c.bankrupt_on - timedelta(days=60):
                break
            seq += 1
            form = "10-K" if fq == 4 else "10-Q"
            lag = 75 if form == "10-K" else 40
            if c.bankrupt_on and end >= date(2022, 12, 31):
                lag += 30  # filing late before the bankruptcy
            accepted = end + timedelta(days=lag)
            adsh = f"0000{c.cik:06d}-{accepted.year % 100:02d}-{seq:06d}"
            qlabel = f"{accepted.year}q{(accepted.month - 1) // 3 + 1}"
            bucket = per_quarter.setdefault(qlabel, {"sub": [], "num": []})
            fy = end.year + (1 if end.month > c.fye_month else 0)
            fp = "FY" if fq == 4 else f"Q{fq}"
            bucket["sub"].append("\t".join([
                adsh, str(c.cik), c.name, str(c.sic), "US", "NY", "NEW YORK", "10001", "US", "", "",
                "1-LAF", f"{c.fye_month:02d}{month_end(2021, c.fye_month).day:02d}", form,
                end.strftime("%Y%m%d"), str(fy), fp, accepted.strftime("%Y%m%d"),
                accepted.strftime("%Y-%m-%d 16:05:00.0"), "0", "1", f"x-{adsh}.htm", "1", "",
            ]))
            filings[c.cik].append((adsh, form, accepted, end, ""))

            def emit(tag: str, ddate: date, qtrs: int, value: float) -> None:
                bucket["num"].append("\t".join([
                    adsh, tag, "us-gaap/2023", ddate.strftime("%Y%m%d"), str(qtrs), "USD", "", "",
                    f"{value:.2f}", "",
                ]))

            for comparative in (0, 4):  # current period and the same period one year earlier
                j = idx - comparative
                if j < 0:
                    continue
                e = periods[j][0]
                vals = values[e]
                ytd_q = [values[periods[k][0]] for k in range(j - fq + 1, j + 1) if k >= 0]
                # restatement: Alpha's prior-year revenue in a 10-K is shown 1 % higher
                restated = comparative == 4 and c.cik == 1001 and fq == 4
                for tag, v in vals.items():
                    if tag not in FLOWS:
                        emit(tag, e, 0, v)
                        continue
                    if tag not in YTD_ONLY:
                        emit(tag, e, 1, v)
                    if fq > 1 and len(ytd_q) == fq:
                        factor = 1.01 if restated and tag == "Revenues" else 1.0
                        emit(tag, e, fq, factor * sum(q[tag] for q in ytd_q))
                    elif fq == 1 and tag in YTD_ONLY:
                        emit(tag, e, 1, v)
    for qlabel, rows in per_quarter.items():
        path = out / "src" / f"{qlabel}.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("sub.txt", "\t".join([
                "adsh", "cik", "name", "sic", "countryba", "stprba", "cityba", "zipba", "countryinc",
                "former", "changed", "afs", "fye", "form", "period", "fy", "fp", "filed", "accepted",
                "prevrpt", "detail", "instance", "nciks", "aciks"]) + "\n" + "\n".join(rows["sub"]) + "\n")
            zf.writestr("num.txt", "adsh\ttag\tversion\tddate\tqtrs\tuom\tsegments\tcoreg\tvalue\tfootnote\n"
                        + "\n".join(dict.fromkeys(rows["num"])) + "\n")
            zf.writestr("tag.txt", "tag\tversion\tcustom\tabstract\tdatatype\tiord\tcrdr\ttlabel\tdoc\n"
                        + "\n".join(f"{t}\tus-gaap/2023\t0\t0\tmonetary\t{'D' if t in FLOWS else 'I'}\tD\t{t}\t{t}"
                                    for t in quarter_values(COMPANIES[0], 0)) + "\n")
            zf.writestr("pre.txt", "adsh\treport\tline\tstmt\tinpth\trfile\ttag\tversion\tplabel\tnegating\n"
                        + "\n".join(f"{r.split(chr(9))[0]}\t2\t1\tIS\t0\tH\tRevenues\tus-gaap/2023\tRevenue\t0"
                                    for r in rows["sub"]) + "\n")
    return list(per_quarter), filings


def build_submissions(out: Path, filings: dict[int, list[tuple]]) -> Path:
    path = out / "src" / "submissions.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for c in COMPANIES:
            rows = list(filings[c.cik])
            if c.bankrupt_on:
                rows.append((f"0000{c.cik:06d}-23-900001", "NT 10-K", c.bankrupt_on - timedelta(days=150), None, ""))
                rows.append((f"0000{c.cik:06d}-23-900002", "8-K", c.bankrupt_on, None, "1.03,7.01,9.01"))
                rows.append((f"0000{c.cik:06d}-23-900003", "25-NSE", c.bankrupt_on + timedelta(days=20), None, ""))
            rows.append((f"0000{c.cik:06d}-22-800001", "8-K", date(2022, 5, 2), None, "2.02,9.01"))
            payload = {
                "cik": f"{c.cik:010d}", "entityType": "operating", "sic": str(c.sic),
                "sicDescription": "fixture", "name": c.name, "tickers": [c.name[:4]], "exchanges": ["Nasdaq"],
                "fiscalYearEnd": f"{c.fye_month:02d}{month_end(2021, c.fye_month).day:02d}",
                "stateOfIncorporation": "DE", "lei": None,
                "addresses": {"business": {"city": "NEW YORK", "stateOrCountry": "NY", "zipCode": "10001"}},
                "formerNames": [{"name": c.name.replace("INC", "HOLDINGS"), "from": "2005-01-01T00:00:00.000Z",
                                 "to": "2021-06-30T00:00:00.000Z"}] if c.cik == 1001 else [],
                "filings": {"recent": {
                    "accessionNumber": [r[0] for r in rows], "form": [r[1] for r in rows],
                    "filingDate": [r[2].isoformat() for r in rows],
                    "reportDate": [r[3].isoformat() if r[3] else "" for r in rows],
                    "acceptanceDateTime": [r[2].isoformat() + "T16:05:00.000Z" for r in rows],
                    "items": [r[4] for r in rows],
                }},
            }
            zf.writestr(f"CIK{c.cik:010d}.json", json.dumps(payload))
    return path


def build_gleif(out: Path) -> Path:
    header = ('"LEI","Entity.LegalName","Entity.OtherEntityNames.OtherEntityName.1",'
              '"Entity.LegalAddress.FirstAddressLine","Entity.LegalAddress.City","Entity.LegalAddress.Country",'
              '"Entity.LegalAddress.PostalCode","Entity.HeadquartersAddress.FirstAddressLine",'
              '"Entity.HeadquartersAddress.City","Entity.HeadquartersAddress.Country",'
              '"Entity.HeadquartersAddress.PostalCode","Entity.EntityStatus","Registration.RegistrationStatus",'
              '"Registration.LastUpdateDate"\n')
    rows = "".join(
        f'"{c.lei}","{c.name.title()}","{c.name[:4]}","1 Main St","New York","US","10001","1 Main St",'
        f'"New York","US","10001","ACTIVE","ISSUED","2024-01-02T00:00:00Z"\n'
        for c in COMPANIES if c.lei
    )
    path = out / "src" / "lei2.csv.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("gleif-goldencopy-lei2.csv", header + rows)
    return path


def build_ecb(settings: Settings) -> None:
    days = [date(2019, 1, 1) + timedelta(days=i) for i in range(5 * 366)]
    business = [d for d in days if d.weekday() < 5]
    tbl = pa.table({
        "currency": ["USD"] * len(business),
        "rate_date": business,
        "rate_per_eur": pa.array([1.10 + 0.0001 * (i % 300) for i in range(len(business))]).cast(pa.decimal128(18, 6)),
    }, schema=ecb.SCHEMA)
    write_partition(tbl, settings.raw_root / "ecb" / "rates", {"fetch_date": "2024-01-02"})


def write_empty_esef(settings: Settings) -> None:
    from ingestion import esef
    write_partition(pa.Table.from_pylist([], schema=esef.FILING_SCHEMA), settings.raw_root / "esef" / "filings",
                    {"country": "DE"})
    write_partition(pa.Table.from_pylist([], schema=esef.FACT_SCHEMA), settings.raw_root / "esef" / "facts",
                    {"country": "DE", "filing": "none"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=".ci-data")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    settings = Settings(data_root=out, user_agent="fixture", min_seconds_between_requests=0)
    manifest = Manifest(settings.manifest_path)
    quarters, filings = build_fsds(out)
    for q in sorted(quarters):
        sec_fsds.land_zip(out / "src" / f"{q}.zip", sec_fsds.Quarter.parse(q), settings, manifest)
    sec_submissions.land_zip(build_submissions(out, filings), date(2024, 1, 2), settings, manifest)
    gleif.land_file(build_gleif(out), "lei2", "full", "2024-01-02", settings, manifest)
    build_ecb(settings)
    write_empty_esef(settings)
    # empty relationship file with the right columns
    write_partition(pa.table({c: pa.array([], pa.string()) for c in gleif.RR_COLUMNS.values()}),
                    settings.raw_root / "gleif" / "relationships", {"variant": "full", "publish_date": "2024-01-02"})
    print(f"fixture landing zone written to {out}")


if __name__ == "__main__":
    main()
