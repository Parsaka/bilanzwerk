# Architecture

Six layers, five sources. Data moves top-down: sources land unchanged, the Raw Vault keeps every
version, the Business Vault applies the accounting rules, the marts serve reports and analysis.
Master data feeds the golden company id into the Business Vault; the analysis writes risk scores
back into the marts so Power BI can show them.

```mermaid
flowchart TB
  subgraph S[Sources]
    FSDS[SEC Financial Statement<br/>Data Sets, quarterly]
    SUB[SEC submissions.zip<br/>8-K items, names]
    ESEF[ESEF filings.xbrl.org<br/>xBRL-JSON]
    GLEIF[GLEIF golden copy<br/>LEI + parents]
    ECB[ECB EXR<br/>daily rates]
  end
  subgraph L[1 Landing: Lakehouse Files, Parquet]
    RAW[raw/&lt;source&gt;/&lt;table&gt;/&lt;partition&gt;<br/>+ ingest_manifest]
  end
  subgraph RV[2 Raw Vault]
    HUB[hub_company · hub_filing · hub_concept]
    LNK[link_filing_registrant · link_filing_company<br/>link_fact · link_company_parent · link_presentation]
    SAT[sat_company_sec · sat_company_gleif · sat_filing<br/>sat_fact_value · sat_concept_def · sat_event]
  end
  subgraph BV[3 Business Vault]
    PIT[pit_fact_first_reported · pit_fact_latest · restatements]
    MAP[line item mapping · quarter derivation · TTM]
    FX[EUR conversion: closing / average rate]
    GOLD[golden company bridge]
  end
  subgraph MDM[Master data: Splink on DuckDB]
    SPL[standardise → block → compare → EM → thresholds<br/>stewardship queue → seed]
  end
  subgraph M[4 Marts: Kimball star]
    F[fact_financial_line · fact_kpi · fact_event<br/>fact_wc_opportunity · fact_risk_score · fact_data_quality]
    D[dim_company SCD2 · dim_period · dim_line_item · dim_kpi<br/>dim_sector · dim_scenario · dim_currency · dim_date]
  end
  subgraph A[5 Analysis]
    ML[labels + censoring → features PIT → M0..M3, S1<br/>rolling backtest · bootstrap · SHAP · MLflow]
  end
  subgraph R[6 Consumption]
    PBI[Power BI semantic model<br/>Direct Lake, 11 pages]
    XL[Excel Monatsbericht<br/>CUBE formulas + VBA]
    TB[Tableau Public<br/>WC opportunity]
  end
  S --> L --> RV --> BV --> M
  RV --> MDM --> GOLD
  M --> A -->|risk_scores| M
  M --> R
```

## Layers

| Layer | Where | Materialisation | What happens |
|---|---|---|---|
| Landing | Lakehouse `Files/raw` (local: `data/raw`) | Parquet, Hive partitions | Download, verify (checksum, zip CRC, column contract), land unchanged with explicit types, manifest row. Idempotent. |
| Staging | Warehouse schema `staging` | views | One model per source table: rename, type, hash keys and hash diffs, company totals only (`segments` and `coreg` empty). |
| Raw Vault | `raw_vault` | incremental, insert-only | Hubs, links, satellites with own macros (ADR-004). Full history; reruns insert nothing. |
| Business Vault | `business_vault` | tables | Point-in-time views, restatements, line item mapping (63 items, 199 tag mappings), quarter derivation and TTM, EUR conversion, golden company bridge. |
| Marts | `marts` | tables | Kimball star (ADR-005), KPI facts with sector percentiles and red flags, WC opportunity, data quality scorecard, Tableau extract. |
| Analysis | Python (`analysis/`) | Parquet write-back | Labels, censoring, leakage guard, rolling backtest, bootstrap, SHAP, MLflow; `risk_scores` back into `fact_risk_score`. |

## Key design points

- **Point-in-time.** `pit_fact_first_reported` keeps, for every company, concept, period end,
  duration and unit, the value from the earliest accepted filing. Every 10-K repeats last
  year's numbers; repeats and restatements never replace the first value. `version` is part of
  the fact grain. KPIs carry `available_at`, the latest acceptance time of any input.
- **Quarter derivation.** FSDS rounds period ends to month ends (ESEF is rounded the same way),
  so the previous year-to-date period ends exactly three month ends earlier: Q2 = H1 - Q1,
  Q3 = 9M - H1, Q4 = FY - 9M. TTM = the reported year, else the sum of four quarters.
- **One code base, two engines.** The same dbt project builds on Fabric and on DuckDB
  (ADR-003). CI builds the whole DAG on a synthetic fixture on every pull request.
- **Golden company id.** Hash key of the LEI when matched, otherwise of the CIK; all facts join
  through `bv_company_golden`, so a later match moves history to the golden record without
  reloading anything.

## Repository map

| Folder | Content |
|---|---|
| `ingestion/` | Loaders `sec_fsds`, `sec_submissions`, `esef`, `gleif`, `ecb`, shared HTTP / manifest / Parquet code, pytest |
| `dbt/` | Staging, raw vault, business vault, marts, seeds, macros, unit and singular tests |
| `mdm/` | Splink matching, review sampler, evaluation |
| `analysis/` | Labels, features, models, backtest, lead time, answer, MLflow |
| `fabric/` | Data Factory pipeline definitions, notebooks |
| `powerbi/` | PBIP project (TMDL semantic model), BPA rules, DAX notes |
| `excel/` | Management report build script and VBA module (`.bas`) |
| `tableau/` | Dashboard specification and extract instructions |
| `infra/terraform/` | Azure and Fabric resources |
| `docs/` | ADRs, runbook, data contracts, data classification, accuracy check |
