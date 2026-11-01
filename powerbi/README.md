# Power BI: semantic model and report (PBIP)

```
powerbi/
  model.yml                       relationships, measures, calculation groups, field parameter, RLS/OLS
  report/pages.yml                the 11 pages: question (DE/EN), main visuals, measures
  tools/generate_tmdl.py          model.yml + docs/data-contracts -> Bilanzwerk.SemanticModel (TMDL)
  tools/generate_report.py        pages.yml -> Bilanzwerk.Report (all 11 pages) + report-pages.md
  tools/visuals.py                PBIR visual builder (fields, sort, filters, colours, titles)
  schemas/                        Microsoft PBIR JSON schemas used by check_pbip.py (MIT licence)
  tools/check_pbip.py             static checks, runs on every pull request (Linux)
  bpa/rules.json                  Tabular Editor Best Practice Analyzer rules (Windows CI job)
  Bilanzwerk.pbip                 open this in Power BI Desktop
  Bilanzwerk.SemanticModel/       generated, do not edit by hand
  Bilanzwerk.Report/              generated from report/pages.yml, do not edit by hand
  report-pages.md                 page spec (generated)
```

## One source of truth

Columns come from the data contracts (`docs/data-contracts/*.yml`), which CI compares with the
warehouse. A renamed mart column fails the contract check first; regenerating the model then
picks it up. Measures, relationships and security live in `model.yml`, so a model change is a
readable diff in a pull request instead of a binary `.pbix` change.

```bash
uv run python powerbi/tools/generate_tmdl.py
uv run python powerbi/tools/generate_report.py
uv run python powerbi/tools/check_pbip.py
```

Both generators overwrite what they own: model changes go into `model.yml`, page layout into
`report/pages.yml` (`layout`: visual type, position, fields as `table.column` or
`table.[Measure]`, sort, filters, title). A change made in Desktop and saved is lost on the next
run unless it is carried back into `pages.yml`.

Chart titles never hold a typed number. A title is either a bilingual label (`label`, rendered
as a measure in `Sprache`) or a finding measure computed from the data (`title`, folder
`Beschriftungen`), e.g. `[Befund Vorlaufzeit]` or `[Befund Cash-Potenzial]`. The answer page
reads H1 to H4 from `fact_hypothesis_result`, which the model run writes.

## Model

* **Storage mode:** Direct Lake on the Fabric Warehouse (`marts` schema). The endpoint in
  `expressions.tmdl` is a placeholder (`#{SQL_ENDPOINT}#`, `#{WAREHOUSE}#`) that the deployment
  pipeline replaces per stage (dev, prod).
* **Base measure chain:** `[_Betrag Roh]` reads EUR or local currency (calculation group
  *Währung*), `[_Betrag Szenario]` defaults to IST unless the *Szenario* group or a slicer picks
  another scenario, `[Betrag]` defaults to the latest version (after restatements). Every
  financial measure is built on `[Betrag]` (flows) or `[Bestand]` (balances at period end), so
  the three calculation groups work on all of them.
* **Calculation groups:** Zeitintelligenz (Ist, Vorjahr, Abweichung, YTD, TTM), Szenario (Ist,
  Plan, Plan-Ist-Abweichung abs/%, Forecast), Währung (EUR, Lokal).
* **Field parameter:** *KPI-Auswahl* drives both axes of the peer scatter (page 6).
* **Language:** German by default; the *Sprache* table switches titles and footer to English
  (synced slicer on every page). Measures are named in German, the glossary in `dim_kpi` has both.
* **Security:** role *Sektor-Team* (RLS) filters `dim_sector` through `sector_team_users`
  (a dbt seed, maintained by pull request); role *Reporting* (OLS) hides
  `fact_risk_score[top_3_drivers]`. Test in Desktop with *View as* or in the service with
  *Test as role* before every release.

## DAX notes

* Ratios use `DIVIDE`, never `/`; the BPA rule `BW_USE_DIVIDE` flags regressions.
* Averages over days (DSO, DIO, DPO) use average balances of the period's opening and closing
  values, as defined in `dim_kpi` and `int_kpi_wide`. The model measures recompute them for any
  aggregation level; the mart values in `fact_kpi` are per company and period and back the
  percentile and red-flag columns.
* Percentiles and red flags are computed in dbt (`fact_kpi`), not in DAX: they need the whole
  sector, which a filtered visual does not have.
* `[Risiko 12M]` averages calibrated probabilities. It is a mean probability, not a share of
  companies; the share of red companies is `[Unternehmen rot]`.

## Performance

Measured in Power BI Desktop with DAX Studio (server timings, cold cache) on the local import
copy of run 41328368604, not on Direct Lake. Every page, the before/after of each change and
the machine: [docs/performance-local.md](../docs/performance-local.md).

| Visual (page) | Before (ms) | Change | After (ms) |
|---|---|---|---|
| Restatement-Quote card (P11) | 67 449 | `fact_kpi.is_restated` computed in dbt instead of iterating versions in DAX | 101 |
| Risk table (P7) | 22 099 | latest as_of_date per company via TREATAS pairs, HASONEVALUE fast path | 11 801 |

The risk table is still formula-engine bound; an `is_latest_for_company` flag in dbt is the
next step.

Candidate changes, in the order to try: remove high-cardinality text columns from facts
(`source_filing` is already hidden; drop it from the model if VertiPaq shows a large
dictionary), replace iterators over `fact_financial_line` with pre-aggregated columns in dbt,
check for Direct Lake fallback to DirectQuery (DAX Studio shows it) and add an aggregation table
where it happens.

## Quality gate

* `tools/check_pbip.py` (every pull request, Linux): measure descriptions, folders and formats,
  hidden foreign keys, DAX references resolve, relationship/RLS/OLS targets exist, no calculated
  columns, date table marked, 11 report pages with title and footer, every visual binding
  exists in the model. Tests in `powerbi/tests`.
* Tabular Editor 2 BPA with `bpa/rules.json` (Windows job in `ci.yml`): the build fails on any
  severity-3 rule.

## Checked in Power BI Desktop

All 11 pages were opened against the real data and compared with `answer.json` of the run;
the screenshots are in [docs/images](../docs/images/) (`powerbi_01_antwort.png` …
`powerbi_11_datenqualitaet.png`). Known cosmetic points: the waterfall legend uses Power BI's
default names (Increase/Decrease/Total), the risk drivers on P7 show raw codes, and Desktop
with an English UI shows "bn"/"M" instead of "Mrd."/"Mio.".

## Local copy without Fabric

The same model in import mode, for Power BI Desktop on one PC (screenshots, DAX Studio) before a
Fabric workspace exists:

1. Download the artifact `marts-parquet` of a real-data run (one Parquet file per mart table):
   `gh run download <run id> -R Parsaka/bilanzwerk -n marts-parquet -D C:\bilanzwerk-marts`.
2. `uv run python powerbi/tools/generate_tmdl.py --local --marts-folder C:\bilanzwerk-marts`
   writes `powerbi/local/` (not versioned): the model with import partitions from Parquet, the
   report bound to it and `Bilanzwerk.Local.pbip`.
3. Open `powerbi/local/Bilanzwerk.Local.pbip` in Power BI Desktop and refresh.

Measures, relationships, roles and pages are the ones of the Direct Lake model; only the
partitions differ. Timings measured here are import-mode timings on a PC, not Direct Lake.

After regenerating with `--local`, delete `powerbi/local/*/.pbi` (Desktop's cache) so Desktop
reads the new model instead of the cached one.
