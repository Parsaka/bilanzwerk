# Tableau Public: Working-Capital-Potenzial nach Sektor

One dashboard on a flat extract, for the job ads that ask for Tableau. It shows the same numbers
as page 9 of the Power BI report (hypothesis H4), from the same mart.

* **Data:** `marts.extract_tableau_wc_opportunity` (dbt), one row per company and fiscal year with
  DSO, DIO, DPO, CCC, the sector medians, revenue in EUR and the cash opportunity (median and
  stretch scenario).
* **Export:** `uv run python scripts/export_tableau.py --duckdb "$BW_DATA_ROOT/bilanzwerk.duckdb"`
  (or `--odbc` against the Fabric Warehouse) writes `tableau/data/wc_opportunity.csv` and a
  manifest with row count, years and SHA-256. The CSV is not versioned; the manifest of the
  published export goes into the release notes.
* **Workbook:** `uv run python tableau/build_workbook.py` packs the CSV into
  `tableau/Bilanzwerk_Working_Capital.twbx` with the sheets, calculated fields and the dashboard
  below; the title is computed from the same CSV. `--check-answer answer.json` fails when the
  workbook total is more than EUR 0.5 bn away from H4. The real-data run builds it and keeps it
  under `results/tableau/` on branch `real-data-results`; publishing it to Tableau Public needs
  the account and stays a manual step.
* **Link:** _added after publishing (Tableau Public profile of Parsa Kamali)._

## Calculated fields

```text
// Szenario (parameter, string): "Median" | "Oberes Quartil"
[Cash-Potenzial EUR] =
    IF [Szenario] = "Median" THEN [cash_opportunity_eur] ELSE [cash_opportunity_stretch_eur] END

[Cash-Potenzial Mrd. EUR] = SUM([Cash-Potenzial EUR]) / 1e9

[Δ DSO] = [dso] - [sector_median_dso]          // positive: collects slower than the sector
[Δ DIO] = [dio] - [sector_median_dio]
[Δ DPO] = [sector_median_dpo] - [dpo]          // positive: pays faster than the sector

[Rang im Sektor] = RANK_DENSE(SUM([Cash-Potenzial EUR]), 'desc')   // table calc, compute by company within sector

[Ist letztes Jahr] = [fiscal_year] = { FIXED : MAX([fiscal_year]) }
```

## Sheets and dashboard (1200 x 800, fixed)

| Sheet | Marks | Rows / columns | Notes |
|---|---|---|---|
| Brücke nach Sektor | Bar (horizontal) | `sector_de` by `[Cash-Potenzial Mrd. EUR]`, sorted descending | Accent colour for the largest sector, grey for the rest; label in Mrd. EUR with one decimal |
| Top 20 Unternehmen | Bar | `company_name` by `[Cash-Potenzial EUR]`, filter top 20 by the same field | Tooltip: sector, revenue, DSO/DIO/DPO against the sector median |
| Wo das Cash liegt | Bar (diverging) | Measure Names `[Δ DSO]`, `[Δ DIO]`, `[Δ DPO]` by sector, median over companies | Shows which lever (receivables, inventory, payables) drives each sector |
| KPI-Zeile | Text | Total `[Cash-Potenzial Mrd. EUR]`, companies, sectors | Above the charts |

Filters and controls: fiscal year (single value, default `[Ist letztes Jahr]`), sector
(multiple values, applied to all sheets), parameter *Szenario*. Clicking a sector in the bridge
filters the top-20 list (dashboard action).

Design rules as in the Power BI report: one accent colour (#1F5AA6) for the item the title talks
about, grey for the rest, no red/green (no risk bands here). The dashboard title states the
finding and is written after the real-data run, for example in the form
"<Sektor> bindet <x> Mrd. EUR mehr Working Capital als der Sektormedian", with the number from
`analysis/results/wc_opportunity_by_sector.csv`. Footer: data cut-off from the manifest, sources
(SEC EDGAR, ESEF via filings.xbrl.org, GLEIF, EZB), link to the repository.

## Method notes for the dashboard caption

* Opportunity per company and fiscal year = max(0, DSO - sector median) x revenue TTM / 365
  + max(0, DIO - sector median) x COGS TTM / 365 + max(0, sector median DPO - DPO) x COGS TTM / 365,
  in EUR. The stretch scenario uses the sector's 25th percentile for DSO and DIO and the 75th for
  DPO. Days outside 0 to 730 are left out as data errors. Definition: `fact_wc_opportunity`,
  currency conversion: ADR-008.
* Sectors with fewer than five companies in a year get no median (dbt var `wc_min_sector_peers`)
  and no opportunity, so a thin sector cannot produce a large number from a single peer.
* Banks and insurers (SIC 6000-6799) are excluded: their balance sheets have no comparable
  working capital.
