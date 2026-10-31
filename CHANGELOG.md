# Changelog

## Week 7 build: reporting, platform, operations (2026-10-27)

- Power BI: semantic model rendered from `powerbi/model.yml` and the data contracts (TMDL, Direct
  Lake), bilingual titles and footer, report scaffold with the 11 pages (PBIR), BPA rules,
  `check_pbip.py` with tests. `Risiko 12M` now shows the champion model at the latest as-of
  date (`fact_risk_score.is_champion`, ADR-007).
- Excel: cockpit with CUBE formulas and XLOOKUP, Windows script for connection, Power Query,
  PivotTable with slicers and the VBA module; VBA kept as CRLF/Windows-1252 `.bas` in Git.
- Tableau: extract export with manifest, dashboard specification.
- Terraform: Azure stack (validated) and Fabric stack; GitHub OIDC, groups, budget alerts.
- Fabric: notebooks and pipelines in Git format, publish to dev/prod with fabric-cicd
  (ADR-009 amendment), pipeline runner and job summary; scheduled loads in GitHub Actions
  because a paused capacity cannot run Fabric schedules.
- GitHub Actions: `ci`, `dbt-build`, `quarterly-load`, `daily-load`, `capacity-pause`,
  `terraform`; SQLFluff config, models reformatted.
- Fixes found on the way: `bw_float` is DOUBLE on DuckDB (FLOAT was 32-bit and rounded large
  amounts); the FSDS loader checks all tables of a zip before writing any (a contract break in
  `num.txt` could leave a new `sub` partition next to the old `num`); GLEIF picks the delta
  window covering the time since the last load.
- Incident drill run on the CI fixture (`docs/incident-drill.md`): detection, fix with
  `COLUMN_ALIASES`, rerun of one quarter, marts identical afterwards.

## Week 1-6 build (2026-10-27)

- ADR-001 (hypotheses, event definition) dated 2026-10-27, before any modelling; ADR-002 to
  ADR-010.
- Loaders for SEC FSDS, SEC submissions, ESEF, GLEIF and ECB with manifest, checksum skip,
  column contracts and privacy filter; 17 pytest tests.
- dbt project (68 models, 9 seeds): staging, Data Vault 2.0 with own macros, Business Vault
  (point-in-time, restatements, line item mapping, quarter derivation, EUR), Kimball marts,
  data quality scorecard; 211 dbt tests and unit tests green on the CI fixture.
- Master data: Splink matching to GLEIF, golden record with survivorship, stewardship queue,
  SCD2 `dim_company`.
- Analysis: labels with censoring, leakage guard, M0-M3 and S1, rolling backtest, bootstrap,
  lead time, SHAP, MLflow, risk-score write-back.
- Not yet done: first load of the real data (see README status).
