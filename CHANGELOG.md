# Changelog

## Power BI Desktop, Tableau Public, measure fixes (PR #6 to PR #10, 2026-11-01)

- Local Power BI copy: `generate_tmdl.py --local` builds an import model from the
  `marts-parquet` artifact; all 11 pages checked in Desktop against `answer.json` of run
  41328368604, screenshots in `docs/images/powerbi_*.png`.
- Measures: `fact_kpi.is_restated` in dbt (Restatement-Quote 67,4 s → 0,1 s); Risiko 12M and
  Unternehmen rot at each company's latest as_of_date (risk table 22,1 s → 11,8 s); WAPE
  replaces MAPE; CCC sector median over bounded peers (≥ 5); KPIs at the latest statement;
  DQ target and status; 149 measures. Timings: `docs/performance-local.md`.
- Tableau: the workbook ships a `.hyper` extract and a valid `<windows>` section; published on
  Tableau Public (link in `tableau/README.md`).
- Docs: README "Was noch fehlt" now lists only Excel `.xlsm` (not run, no licence),
  Azure/Fabric, the human spot-check and the open data findings.

## Real data, master data review, fixes found in the results (PR #2, PR #3, 2026-10-31 to 2026-11-01)

- Master data: 300 candidate pairs labelled blind by written rules (`mdm/REVIEW.md`); model v1
  reached precision 0.20 / recall 0.35 at 0.90. Model v3 (ADR-006 amendment): name levels for
  series marks and name extensions, legal-form comparison, m from the labels, auto-match only
  on an exact or near-exact name without contradicting legal form or tie. Holdout of 149 fresh
  pairs: precision 1.00, recall 1.00. Golden records are reproducible (ties ordered by LEI).
- Point-in-time: every KPI is dated by its own inputs, not by the latest item of the period;
  the first-reported version keeps the tag known first (a tag switch such as ASC 606 had
  dated two prior years of revenue to the later 10-K).
- Label audit: `bw-analysis label-audit` reads every 8-K behind the bankruptcy label on EDGAR;
  124 of 3 609 have no Item 1.03 in the text and 250 name only a subsidiary as debtor
  (wording heuristic). Reported, the label is unchanged (ADR-001).
- H1 sensitivity on computable quarters only, next to the pre-registered measurement.
- Tableau: the extract joined every SCD2 version of a company and counted its potential up to
  three times; it now joins the current name, and the run checks the workbook against H4.
  `tableau/build_workbook.py` packs the `.twbx`.
- Data quality: `SCALE_OUTLIER_TOTAL_ASSETS` compares against both neighbouring periods,
  `MDM_LEI_MATCH_RATE` counts only filers with periods, an `--empty` build no longer appends
  rows; results of the run in `docs/data-quality-results.md`.
- Real-data run: base build single-threaded (DuckDB temp disk), exports of data-quality rules
  and MDM counts, case-study events. Results: README and `docs/management-summary` from run
  41282080293; case studies in `docs/case-studies.md`.

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
