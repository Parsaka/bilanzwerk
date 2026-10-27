# Bilanzwerk

**Financial-Reporting- und Frühwarnplattform auf offiziellen Unternehmensabschlüssen**
(SEC, ESEF, GLEIF, EZB) · Data Vault 2.0 · Kimball · dbt · Microsoft Fabric · Power BI

[Deutsch](#deutsch) · [English](#english)

---

## Die Antwort / The answer

> **Status: noch offen.** Die Pipeline ist gebaut und getestet; der erste vollständige Lauf auf
> den echten SEC-Daten steht aus. Hier stehen danach die vier Zeilen aus
> `data/analysis/results/answer.json`, jede mit Zahl und 95%-Konfidenzintervall.
> Die Hypothesen wurden vorher festgelegt: [ADR-001](docs/adr/ADR-001-hypotheses.md) (27.10.2026).
>
> **Status: pending.** The pipeline is built and tested; the first full run on the real SEC data
> is outstanding. The four answer lines (each with its number and 95 % interval) will replace
> this box. Hypotheses were fixed beforehand in ADR-001 (2026-10-27).

| | Hypothese | Ergebnis | Zahl | 95%-KI |
|---|---|---|---|---|
| H1 | Working Capital (CCC) warnt früher als Altman Z'' | offen | – | – |
| H2 | Z''-Kennzahlen + Working Capital schlagen Z'' allein (PR-AUC) | offen | – | – |
| H3 | Sektorrelative Kennzahlen schlagen absolute | offen | – | – |
| H4 | Working-Capital-Potenzial je Sektor ist wesentlich (Mrd. EUR) | offen | – | – |

---

## Deutsch

### Worum es geht

Bilanzwerk beantwortet eine Frage, die sich Kreditabteilungen, Wirtschaftsprüfer und
Controller gleichermaßen stellen:

> Welche veröffentlichten Kennzahlen warnen am frühesten und zuverlässigsten, dass ein
> börsennotiertes Unternehmen innerhalb von 12 Monaten insolvent wird – und warnt eine
> Verschlechterung des Working Capitals früher als der klassische Altman-Z-Score?

und eine zweite, die der Antwort einen Euro-Wert gibt:

> Wie viel Liquidität könnte jeder Sektor freisetzen, wenn seine Unternehmen den Cash
> Conversion Cycle auf den Sektormedian senken?

### Was gebaut ist

| Baustein | Inhalt |
|---|---|
| Ingestion | Lader für SEC Financial Statement Data Sets (seit 2009), SEC submissions (8-K Item 1.03, Form 15/25), ESEF, GLEIF, EZB. Manifest mit SHA-256, idempotent, Spaltenverträge, Datenschutzfilter. |
| Raw Vault | Data Vault 2.0 mit eigenen dbt-Makros (Hubs, Links, Satelliten, PIT), SHA-256-Hashkeys, identisch auf DuckDB und Fabric. |
| Business Vault | Point-in-time (Erstveröffentlichung vs. letzter Stand), Restatements, Mapping von US-GAAP/IFRS auf 63 Positionen, Quartalsableitung aus YTD, TTM, EUR-Umrechnung (Stichtags-/Durchschnittskurs). |
| Stammdaten | Abgleich SEC ↔ GLEIF mit Splink, Golden Record, Survivorship, Stewardship-Queue, SCD Typ 2. |
| Marts | Kimball-Sternschema: Finanzzeilen (Ist/Plan/Forecast), 25 KPIs mit Sektorperzentil und roter Flagge, Ereignisse, Working-Capital-Potenzial, Risikoscores, Datenqualität. |
| Analyse | Labels mit Zensierung, Leakage-Schutz, Modelle M0–M3 und Survival-Modell S1, rollierender Backtest, Bootstrap, SHAP, MLflow. |
| Reporting | Power-BI-Projekt (PBIP): Semantikmodell aus `model.yml` und den Datenverträgen generiert (58 Messungen, Berechnungsgruppen, Feldparameter, RLS/OLS, DE/EN), 11 Seiten mit Titel, Sprachumschalter und Fußzeile, BPA-Regeln. Excel-Monatsbericht (CUBE-Formeln, XVERWEIS, Power Query, Pivot mit Datenschnitten, VBA-Export als PDF). Tableau-Extrakt und Dashboard-Spezifikation. |
| Betrieb | Fabric-Pipelines und Notebooks (je Quelle, Transform, Master, E-Mail-Alarme), Veröffentlichung nach dev/prod mit fabric-cicd, GitHub Actions (CI, dbt-Build, Quartals- und Tageslauf, Kapazität pausieren, Terraform), Terraform für Azure und Fabric (OIDC, keine Secrets), Runbook, Incident-Drill, Datenverträge. |

### Ergebnisse in Zahlen

Werden nach dem ersten vollständigen Lauf eingetragen; Platzhalter bleiben leer, bis die Zahl
gemessen ist.

| Messgröße | Wert |
|---|---|
| Zeilen Abschlusswerte (FSDS `num`, Konzernsummen) | – |
| Unternehmen / Filings | – |
| Ladezeit Vollhistorie | – |
| Mapping-Abdeckung (us-gaap) | – |
| Bilanzcheck bestanden (Ziel ≥ 98 %) | – |
| LEI-Match-Quote / Precision / Recall (300 geprüfte Paare) | – |
| PR-AUC M0 / M1 / M2 / M3 | – |
| Abfragezeit langsamste Visuals vorher → nachher | – |
| Monatliche Kosten (Kapazität + Speicher) | – |

### Schnellstart

```bash
uv sync --all-extras
uv run pytest                                   # 66 Tests
uv run python scripts/build_test_landing.py --out .ci-data   # synthetische Testdaten
cd dbt && BW_DATA_ROOT=../.ci-data DBT_PROFILES_DIR=. uv run dbt build
```

Vollständiger Lauf mit echten Daten: [docs/runbook.md](docs/runbook.md).

### Was noch fehlt

Ehrlich aufgeführt, damit niemand eine Zahl für gemessen hält, die es nicht ist:

- **Erster Lauf auf echten Daten** (SEC, ESEF, GLEIF, EZB): danach Antwortbox, Ergebnistabelle,
  Fallstudien und Diagrammtitel. Alles bis dahin läuft auf einem synthetischen CI-Fixture.
- **300 Paare von Hand prüfen** für Precision/Recall des Stammdatenabgleichs (`mdm/`).
- **Power BI Desktop:** Hauptvisuals je Seite nach `powerbi/report-pages.md` platzieren,
  Screenshots, DAX-Studio-Messung vorher/nachher.
- **Excel unter Windows:** `excel/finalize_workbook.ps1` erzeugt die `.xlsm` mit Verbindung,
  Power Query, Pivot und VBA.
- **Tableau Public:** Dashboard nach `tableau/README.md` bauen und veröffentlichen.
- **Azure/Fabric:** Terraform anwenden, Repository-Variablen setzen; die Fabric-Items wurden
  gegen das Git-Format und fabric-cicd geprüft, aber noch in keinem Workspace ausgeführt.

---

## English

### What it is

Bilanzwerk is a financial reporting and early-warning platform built on official company
filings. It answers two questions with evidence:

1. Which published KPIs warn earliest and most reliably that a listed company will go bankrupt
   within 12 months, and does a worsening of working capital warn earlier than the Altman
   Z-score?
2. How much cash could each sector free up by bringing its cash conversion cycle down to the
   sector median?

Readers: a credit analyst at a bank, a finance and reporting consultant, a controller, a BI
engineering lead. Each finds their daily work in it.

### How the answer stays honest

- Hypotheses, metrics and the "held" criterion were written down before any test data was
  looked at ([ADR-001](docs/adr/ADR-001-hypotheses.md)).
- The model only sees **first-reported** values, at the **acceptance date** of each statement;
  a leakage guard fails the run otherwise.
- **Rolling yearly out-of-time** splits, never random; PR-AUC, recall in the top 5 %, Brier
  score; 1,000 bootstrap resamples over companies for every difference.
- Companies that stop filing without an event are censored, not counted as healthy.
- A negative result is reported as a result.

### Architecture

See [docs/architecture.md](docs/architecture.md). In short: sources land unchanged as Parquet,
a Data Vault 2.0 raw layer keeps every version, the Business Vault applies point-in-time,
mapping, quarter derivation and currency rules, a Kimball star serves Power BI, Excel and the
analysis, and the model writes risk scores back. The same dbt project builds on Microsoft
Fabric and on DuckDB, so every pull request builds and tests the full DAG.

### Decisions

| ADR | Decision |
|---|---|
| [001](docs/adr/ADR-001-hypotheses.md) | Hypotheses, event definition, success criteria |
| [002](docs/adr/ADR-002-data-sources.md) | SEC FSDS + submissions as backbone, ESEF as second scope, GLEIF, ECB |
| [003](docs/adr/ADR-003-platform.md) | Microsoft Fabric; same dbt project on DuckDB for CI and fallback |
| [004](docs/adr/ADR-004-data-vault.md) | Data Vault 2.0 with own macros and hash convention |
| [005](docs/adr/ADR-005-serving-and-bi.md) | Kimball star; Power BI, Excel, Tableau |
| [006](docs/adr/ADR-006-master-data-matching.md) | Splink matching to GLEIF, thresholds, stewardship |
| [007](docs/adr/ADR-007-models-and-evaluation.md) | Models M0-M3, S1 and the evaluation protocol |
| [008](docs/adr/ADR-008-currency.md) | EUR with ECB closing and average rates |
| [009](docs/adr/ADR-009-orchestration-and-infrastructure.md) | Fabric Data Factory, GitHub Actions, Terraform |
| [010](docs/adr/ADR-010-data-quality-and-contracts.md) | Data quality rules, tests, data contracts |

### Repository

```
ingestion/        loaders + pytest           dbt/            staging, raw_vault, business_vault, marts, seeds, tests
mdm/              Splink matching            analysis/       labels, features, models, backtest
fabric/           pipelines, notebooks       powerbi/        PBIP project, generators, BPA rules, checks
excel/            cockpit builder, VBA (.bas) tableau/        dashboard spec, extract export
scripts/          fixture, contracts, drill, Fabric publish/run, capacity
infra/terraform/  Azure + Fabric             docs/           ADRs, runbook, contracts, classification
```

### Data sources and licences

SEC EDGAR data (public, U.S. government work), filings.xbrl.org ESEF data ("no restrictions on
the ways that the data can be used"), GLEIF LEI data (CC0), ECB statistics (free reuse with
source attribution). Contact-person fields from GLEIF are removed at ingestion
([data classification](docs/data-classification.md)).
