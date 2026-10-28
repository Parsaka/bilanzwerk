# ADR-010: Data quality rules, tests and data contracts

- Status: accepted
- Date: 2026-10-27

## Context

The spec names dbt tests and dbt-expectations. dbt-expectations has no maintained support for
the Fabric adapter, and the hub (hub.getdbt.com) is not reachable from every build network.

## Decision

- Own generic tests in `dbt/macros/tests/generic_tests.sql` cover what dbt-expectations would:
  `unique_combination`, `values_between`, `matches_iso_currency`, `row_count_reconciles`,
  `pass_rate_at_least`, `hash_is_sha256_hex`, `scd2_no_overlap`, `no_overlapping_sic_ranges`.
- `fact_data_quality` appends one row per run, rule and table (completeness, validity,
  uniqueness, consistency, timeliness, master data) for the Power BI data quality page.
- Hard gates in dbt tests: grain uniqueness, referential integrity, balance check >= 98 %,
  no look-ahead, hash convention, plan frozen before its year.
- Data contracts in `docs/data-contracts/*.yml` (columns with logical types, grain, freshness,
  owner, breaking-change rule). `scripts/check_contracts.py` runs in CI and fails on a removed
  or retyped column; additive columns pass.
- Accuracy spot check: 20 random company-years compared by hand with the filed statement in
  `docs/accuracy-check.md`.
