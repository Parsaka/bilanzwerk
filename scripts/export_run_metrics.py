"""Write the measured run metrics the README quotes: data-quality rules and MDM counts.

uv run python scripts/export_run_metrics.py --duckdb data/bilanzwerk.duckdb --out data/results
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duckdb", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.duckdb), read_only=True)
    con.execute("select * from marts.fact_data_quality order by rule_code").df().to_csv(
        args.out / "data_quality.csv", index=False
    )
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    metrics = {
        "sec_filers_considered": one(
            "select count(*) from staging.stg_sec_submissions__companies as c "
            "where c.hk_company in (select hk_company from business_vault.bv_company_periods)"
        ),
        "matches_by_status": dict(
            con.execute(
                "select match_status, count(*) from read_parquet(?) group by 1 order by 1",
                [str(args.duckdb.parent / "mdm" / "company_matches.parquet")],
            ).fetchall()
        ),
        "golden_records_with_lei": one(
            "select count(distinct golden_company_id) from business_vault.bv_company_golden where lei is not null"
        ),
        "stewardship_queue_open": one("select count(*) from marts.fact_stewardship_queue"),
        # one LEI on more than one golden record would be a duplicate the MDM failed to merge
        "duplicate_golden_records": one(
            "select count(*) from (select lei from marts.dim_company where is_current = 1 and lei is not null "
            "group by lei having count(distinct company_id) > 1)"
        ),
    }
    (args.out / "mdm_metrics.json").write_text(json.dumps(metrics, indent=2, default=int))
    print(json.dumps(metrics, indent=2, default=int))


if __name__ == "__main__":
    main()
