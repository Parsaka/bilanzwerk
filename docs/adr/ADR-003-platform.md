# ADR-003: Platform: Microsoft Fabric, with the same dbt project running on DuckDB

- Status: accepted
- Date: 2026-10-27

## Options

Microsoft Fabric; Databricks; Azure SQL plus Power BI; Snowflake.

## Decision

Microsoft Fabric (Lakehouse for landed files, Warehouse as the dbt target, Data Factory
pipelines, Power BI with Direct Lake). Databricks is already shown in TransitPulse; Fabric is the
gap the job ads ask for.

The dbt project is written so that it also builds on **DuckDB** over the landed Parquet files.
Every SQL difference goes through a dispatched macro (`dbt/macros/cross_db/`): hashing,
percentiles, month ends, integer division, string types. This gives:

- a full `dbt build` in CI on a small fixture without a Fabric capacity (fast, free, every PR);
- local development on a laptop against the real Parquet files;
- a working fallback if the Fabric trial ends (with `dbt-sqlserver` on Azure SQL as the second
  fallback named in the spec).

## Consequences

- No dbt packages that lack Fabric support (see ADR-010).
- Hash keys are byte-identical on both engines (tested in `assert_hash_convention`), so data
  built locally and in Fabric can be compared row by row.
- SQL style: no `qualify`, no `limit`, no boolean columns, no column aliases in `group by`,
  no nested CTEs; T-SQL and DuckDB both accept the result.
