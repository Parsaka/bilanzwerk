# ADR-005: Kimball star for Power BI and Excel; flat extract for Tableau

- Status: accepted
- Date: 2026-10-27

## Options

One wide table; Kimball star; one big table for Tableau only. Front ends: Power BI only, plus
Excel, plus Tableau, plus Qlik.

## Decision

- Kimball star in `marts`: facts `fact_financial_line`, `fact_kpi`, `fact_risk_score`,
  `fact_event`, `fact_wc_opportunity`, `fact_data_quality`; dimensions `dim_company` (SCD2),
  `dim_line_item`, `dim_period`, `dim_date`, `dim_kpi`, `dim_scenario`, `dim_sector`,
  `dim_currency`.
- `version` (first reported / latest) is part of the fact grain, so the report can show
  restatements and the model can never see them.
- Power BI is the main front end (Direct Lake), Excel management report via Analyze in Excel
  with CUBE formulas, Tableau Public from one flat extract (`extract_tableau_wc_opportunity`).
  Qlik stays optional.
- Facts reference the SCD2 version key (`company_key`) valid at the period end and also carry
  the durable `company_id`.

## Consequences

- Single-direction relationships from dimensions to facts; no calculated columns on facts.
- The Tableau extract is the only denormalised table and exists for one dashboard.
