"""Check the built mart tables against docs/data-contracts/*.yml.

A contract lists columns with logical types, the grain, freshness, owner and the
breaking-change rule. The check fails (exit 1) when a contracted column is missing or its
logical type changed; new columns are reported but allowed (additive change).

  python scripts/check_contracts.py --duckdb .ci-data/bilanzwerk.duckdb
  python scripts/check_contracts.py --write --duckdb ...   # create contracts for new tables only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import yaml

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "docs" / "data-contracts"

LOGICAL = {
    "VARCHAR": "string",
    "CHAR": "string",
    "TEXT": "string",
    "BIGINT": "integer",
    "INTEGER": "integer",
    "SMALLINT": "integer",
    "TINYINT": "integer",
    "HUGEINT": "integer",
    "INT": "integer",
    "BIT": "integer",
    "DOUBLE": "float",
    "FLOAT": "float",
    "REAL": "float",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
    "DATETIME2": "timestamp",
    "DATETIME": "timestamp",
    "BOOLEAN": "integer",
}


def logical_type(db_type: str) -> str:
    base = db_type.upper().split("(")[0].strip()
    if base in ("DECIMAL", "NUMERIC"):
        return "decimal"
    return LOGICAL.get(base, base.lower())


def actual_columns(con: duckdb.DuckDBPyConnection, schema: str) -> dict[str, dict[str, str]]:
    rows = con.execute(
        "select table_name, column_name, data_type from information_schema.columns "
        "where table_schema = ? order by table_name, ordinal_position",
        [schema],
    ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for table, column, dtype in rows:
        out.setdefault(table, {})[column] = logical_type(dtype)
    return out


def check(actual: dict[str, dict[str, str]]) -> list[str]:
    errors = []
    for path in sorted(CONTRACT_DIR.glob("*.yml")):
        contract = yaml.safe_load(path.read_text())
        table = contract["table"]
        cols = actual.get(table)
        if cols is None:
            errors.append(f"{table}: table missing")
            continue
        for col in contract["columns"]:
            name, typ = col["name"], col["type"]
            if name not in cols:
                errors.append(f"{table}.{name}: contracted column missing")
            elif cols[name] != typ:
                errors.append(f"{table}.{name}: type changed {typ} -> {cols[name]}")
        extra = set(cols) - {c["name"] for c in contract["columns"]}
        if extra:
            print(f"note: {table} has new columns (allowed, additive): {sorted(extra)}")
    return errors


def write_missing(actual: dict[str, dict[str, str]]) -> None:
    for table, cols in actual.items():
        path = CONTRACT_DIR / f"{table}.yml"
        if path.exists():
            continue
        contract = {
            "table": table,
            "schema": "marts",
            "owner": "TODO",
            "grain": "TODO",
            "freshness": "new SEC quarter within 24 hours of publication",
            "breaking_change_rule": "Removing or retyping a column needs a new major version and an ADR; "
            "adding a column is allowed.",
            "columns": [{"name": c, "type": t} for c, t in cols.items()],
        }
        path.write_text(yaml.safe_dump(contract, sort_keys=False, allow_unicode=True))
        print(f"wrote {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duckdb", required=True)
    parser.add_argument("--schema", default="marts")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    con = duckdb.connect(args.duckdb, read_only=True)
    actual = actual_columns(con, args.schema)
    if args.write:
        write_missing(actual)
    errors = check(actual)
    for e in errors:
        print(f"CONTRACT BROKEN: {e}")
    print(f"{len(list(CONTRACT_DIR.glob('*.yml')))} contracts checked, {len(errors)} violations")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
