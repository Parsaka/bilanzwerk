"""Export the flat Tableau extract (marts.extract_tableau_wc_opportunity) to tableau/data/.

  uv run python scripts/export_tableau.py --duckdb "$BW_DATA_ROOT/bilanzwerk.duckdb"
  uv run python scripts/export_tableau.py --odbc "Driver={ODBC Driver 18 for SQL Server};Server=<endpoint>;
      Database=<warehouse>;Authentication=ActiveDirectoryInteractive"   (one line)

Writes wc_opportunity.csv (UTF-8, comma, point as decimal separator, ISO dates) and a small
manifest with row count, data cut-off and a SHA-256 of the file, so the published dashboard can
be traced back to one export.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tableau" / "data"
QUERY = "select * from marts.extract_tableau_wc_opportunity order by fiscal_year, sector_de, company_name"


def fetch_duckdb(path: str) -> tuple[list[str], list[tuple]]:
    import duckdb

    con = duckdb.connect(path, read_only=True)
    rel = con.sql(QUERY)
    return rel.columns, rel.fetchall()


def fetch_odbc(conn_str: str) -> tuple[list[str], list[tuple]]:
    import pyodbc

    with pyodbc.connect(conn_str) as con:
        cur = con.cursor().execute(QUERY)
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--duckdb")
    src.add_argument("--odbc")
    args = parser.parse_args()
    columns, rows = fetch_duckdb(args.duckdb) if args.duckdb else fetch_odbc(args.odbc)
    if not rows:
        raise SystemExit("extract is empty: run dbt build first")

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "wc_opportunity.csv"
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(tuple(round(v, 4) if isinstance(v, float) else v for v in r) for r in rows)
    years = [r[columns.index("fiscal_year")] for r in rows]
    manifest = {
        "file": target.name,
        "rows": len(rows),
        "fiscal_years": [min(years), max(years)],
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "duckdb" if args.duckdb else "fabric",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    (OUT / "wc_opportunity.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {target.relative_to(ROOT)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
