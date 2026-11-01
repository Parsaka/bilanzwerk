# Bilanzwerk

**Financial-Reporting- und Frühwarnplattform auf offiziellen Unternehmensabschlüssen**
(SEC, ESEF, GLEIF, EZB) · Data Vault 2.0 · Kimball · dbt · Microsoft Fabric · Power BI

[Deutsch](#deutsch) · [English](#english)

---

## Die Antwort / The answer

> Ergebnis des vollständigen Laufs auf den echten Daten (SEC FSDS 2009q2–2026q3, 1 661
> Insolvenzen nach 8-K Item 1.03, rollierender Backtest 2014–2025, 1 000 Bootstrap-Ziehungen
> über Unternehmen). Die Hypothesen wurden vorher festgelegt:
> [ADR-001](docs/adr/ADR-001-hypotheses.md) (27.10.2026).
> Lauf: [Actions 40684230866](https://github.com/Parsaka/bilanzwerk/actions/runs/40684230866),
> Zahlen: Branch `real-data-results`, `results/analysis/answer.json`.
>
> **H1 nicht bestätigt:** Das CCC-Signal wurde im Median 0,0 Monate vor der Insolvenz rot, das
> Z''-Signal 6,0 Monate; Differenz −6,0 Monate (95%-KI −7,4 bis −4,6).
> **H2 nicht bestätigt:** PR-AUC M2 minus M1 = −0,004 (95%-KI −0,007 bis −0,001).
> **H3 bestätigt:** PR-AUC sektorrelativ minus absolut = +0,009 (95%-KI +0,006 bis +0,012).
> **H4 bestätigt:** Working-Capital-Potenzial gesamt 1 295 Mrd. EUR; größter Hebel Technologie
> und Telekommunikation mit 328 Mrd. EUR.
>
> **English:** the full run on real data. H1 not held: the CCC flag turned red a median 0.0
> months before bankruptcy, Z'' 6.0 months (difference −6.0, 95 % CI −7.4 to −4.6). H2 not held:
> adding working capital to Z'' lowers PR-AUC by 0.004 (CI −0.007 to −0.001). H3 held:
> sector-relative KPIs add 0.009 PR-AUC (CI 0.006 to 0.012). H4 held: EUR 1,295 bn of working
> capital, EUR 328 bn of it in technology and telecoms.

| | Hypothese | Ergebnis | Zahl | 95%-KI |
|---|---|---|---|---|
| H1 | Working Capital (CCC) warnt früher als Altman Z'' | nicht bestätigt | −6,0 Monate | −7,4 bis −4,6 |
| H2 | Z''-Kennzahlen + Working Capital schlagen Z'' allein (PR-AUC) | nicht bestätigt | −0,004 | −0,007 bis −0,001 |
| H3 | Sektorrelative Kennzahlen schlagen absolute | bestätigt | +0,009 | +0,006 bis +0,012 |
| H4 | Working-Capital-Potenzial je Sektor ist wesentlich (Mrd. EUR) | bestätigt | 1 295 | – (Summe, kein Schätzer) |

**Wie man H1 lesen muss.** Von 630 Insolvenzen mit Kennzahlen hatten nur 27 (4 %) je eine rote
CCC-Flagge, aber 399 (63 %) eine rote Z''-Flagge. Wo die CCC-Flagge kam, kam sie im Median
4,7 Monate vorher (Z'': 11,4). Die CCC braucht DSO, DIO und DPO zugleich; ob die
seltenen Flaggen an fehlenden Größen liegen, ist noch nicht ausgewertet. Für die Watchlist
heißt der Befund: Z'' warnt früher und öfter, die CCC-Flagge in ihrer jetzigen Form nicht.
Unternehmen ohne Sektorzuordnung (S99) sind im H4-Potenzial nicht enthalten.

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
| Reporting | Power-BI-Projekt (PBIP): Semantikmodell aus `model.yml` und den Datenverträgen generiert (139 Measures, Berechnungsgruppen, Feldparameter, RLS/OLS, DE/EN), 11 Seiten mit Titel, Sprachumschalter und Fußzeile, BPA-Regeln. Excel-Monatsbericht (CUBE-Formeln, XVERWEIS, Power Query, Pivot mit Datenschnitten, VBA-Export als PDF). Tableau: Extrakt und daraus gepackte Arbeitsmappe (`.twbx`, Titel aus den Daten berechnet und gegen H4 geprüft). |
| Betrieb | Fabric-Pipelines und Notebooks (je Quelle, Transform, Master, E-Mail-Alarme), Veröffentlichung nach dev/prod mit fabric-cicd, GitHub Actions (CI, dbt-Build, Quartals- und Tageslauf, Kapazität pausieren, Terraform), Terraform für Azure und Fabric (OIDC, keine Secrets), Runbook, Incident-Drill, Datenverträge. |

### Ergebnisse in Zahlen

Aus dem Lauf auf echten Daten vom 28.10.2026; Felder mit „–“ sind noch nicht gemessen.

| Messgröße | Wert |
|---|---|
| Zeilen Abschlusswerte (FSDS `num`, 70 Quartale 2009q2–2026q3, geladen) | 188 865 277 |
| Filings (FSDS `sub`) | 440 233 |
| Beobachtungen im Modell / davon mit Label / Insolvenzen | 226 813 / 198 057 / 1 661 |
| Ladezeit Vollhistorie | – |
| Mapping-Abdeckung (us-gaap) | – |
| Bilanzcheck bestanden (Ziel ≥ 98 %) | – |
| LEI-Match-Quote / Precision / Recall (300 geprüfte Paare) | – |
| PR-AUC M0 / M1 / M2 / M3 (gepoolt 2014–2025, 1 403 Ereignisse) | 0,027 / 0,030 / 0,026 / 0,066 |
| PR-AUC M2r (sektorrelativ) / S1 (Hazard) | 0,035 / 0,030 |
| Recall in den riskantesten 5 % M0 / M1 / M2 / M3 | 20 % / 22 % / 17 % / 36 % |
| Abfragezeit langsamste Visuals vorher → nachher | – |
| Monatliche Kosten (Kapazität + Speicher) | – |

### Schnellstart

```bash
uv sync --all-extras
uv run pytest                                   # 103 Tests
uv run python scripts/build_test_landing.py --out .ci-data   # synthetische Testdaten
cd dbt && BW_DATA_ROOT=../.ci-data DBT_PROFILES_DIR=. uv run dbt build
```

Vollständiger Lauf mit echten Daten: [docs/runbook.md](docs/runbook.md).

### Was noch fehlt

Ehrlich aufgeführt, damit niemand eine Zahl für gemessen hält, die es nicht ist:

- **Fallstudien und Diagrammtitel** aus den echten Zahlen. Der Lauf selbst ist erledigt:
  `real-data-run.yml` fährt die ganze Kette auf einem GitHub-Runner und legt die Ergebnisse auf
  den Branch `real-data-results` (Runbook).
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
