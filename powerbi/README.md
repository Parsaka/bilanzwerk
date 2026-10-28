# Power BI: semantic model and report (PBIP)

```
powerbi/
  model.yml                       relationships, measures, calculation groups, field parameter, RLS/OLS
  report/pages.yml                the 11 pages: question (DE/EN), main visuals, measures
  tools/generate_tmdl.py          model.yml + docs/data-contracts -> Bilanzwerk.SemanticModel (TMDL)
  tools/generate_report.py        pages.yml -> Bilanzwerk.Report (PBIR scaffold) + report-pages.md
  tools/check_pbip.py             static checks, runs on every pull request (Linux)
  bpa/rules.json                  Tabular Editor Best Practice Analyzer rules (Windows CI job)
  Bilanzwerk.pbip                 open this in Power BI Desktop
  Bilanzwerk.SemanticModel/       generated, do not edit by hand
  Bilanzwerk.Report/              scaffold generated once, then edited in Desktop
  report-pages.md                 page spec (generated)
```

## One source of truth

Columns come from the data contracts (`docs/data-contracts/*.yml`), which CI compares with the
warehouse. A renamed mart column fails the contract check first; regenerating the model then
picks it up. Measures, relationships and security live in `model.yml`, so a model change is a
readable diff in a pull request instead of a binary `.pbix` change.

```bash
uv run python powerbi/tools/generate_tmdl.py
uv run python powerbi/tools/generate_report.py   # keeps pages already edited in Desktop
uv run python powerbi/tools/check_pbip.py
```

Edits made in Desktop to the semantic model are overwritten by the generator. Make model changes
in `model.yml`; report layout changes in Desktop are kept.

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

## Performance (to be measured on real data)

Procedure from the spec: record the five slowest visuals with DAX Studio (server timings,
cold cache) and VertiPaq Analyzer, tune, record again. The table goes into the main README.

| Visual (page) | Before (ms) | Change | After (ms) |
|---|---|---|---|
| _not measured yet: needs the real data in Fabric_ | | | |

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

## What still needs Power BI Desktop

The generated scaffold has title, language switch, footer and a grey build note per page. The
main visuals (listed in `report-pages.md`) are placed by hand, and chart titles state the
finding, which is only known after the real-data run. Screenshots of all 11 pages go to
`docs/img/report/`. The PBIR files were written against the published Fabric JSON schemas and
checked by `check_pbip.py`, not yet opened in Desktop; open and save once in Desktop to let it
normalise the files before the first commit of hand-made changes.
