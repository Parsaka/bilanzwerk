# Changelog

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
