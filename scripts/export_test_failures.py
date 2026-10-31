"""Write a sample of every stored dbt test failure to CSV (real-data run diagnostics).

python scripts/export_test_failures.py --duckdb data/bilanzwerk.duckdb --out results/test_failures
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--duckdb", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rows", default=200, type=int)
    args = parser.parse_args()
    if not args.duckdb.exists():
        return
    con = duckdb.connect(str(args.duckdb), read_only=True)
    tables = con.execute(
        "select table_schema, table_name from information_schema.tables where table_schema like '%dbt_test__audit'"
    ).fetchall()
    args.out.mkdir(parents=True, exist_ok=True)
    for schema, table in tables:
        n = con.execute(f'select count(*) from "{schema}"."{table}"').fetchone()[0]
        if n:
            df = con.execute(f'select * from "{schema}"."{table}" limit {args.rows}').df()
            df.to_csv(args.out / f"{table}.csv", index=False)
            print(f"{table}: {n} rows")


if __name__ == "__main__":
    main()
