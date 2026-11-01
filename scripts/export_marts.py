"""Export the mart tables the Power BI model reads to Parquet, one file per table.

  uv run python scripts/export_marts.py --duckdb "$BW_DATA_ROOT/bilanzwerk.duckdb" --out data/marts_parquet

The local import-mode model (powerbi/tools/generate_tmdl.py --local) reads these files, so the
report opens in Power BI Desktop without Fabric. The table list comes from powerbi/model.yml.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]


def tables() -> list[tuple[str, str]]:
    model = yaml.safe_load((ROOT / "powerbi" / "model.yml").read_text())
    return [(cfg.get("schema", model["warehouse_schema"]), name) for name, cfg in model["tables"].items()]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--duckdb", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.duckdb), read_only=True)
    manifest = {}
    for schema, name in tables():
        target = args.out / f"{name}.parquet"
        con.execute(f"copy (select * from {schema}.{name}) to '{target}' (format parquet, compression zstd)")
        rows = con.execute(f"select count(*) from {schema}.{name}").fetchone()[0]
        manifest[name] = {"rows": rows, "bytes": target.stat().st_size}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
