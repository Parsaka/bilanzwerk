# Report performance on a local PC

**Import mode in Power BI Desktop 2.156.951.0 on a local PC (Intel Core i5-1135G7, 4 cores /
8 threads, 15.7 GB RAM, Windows 11 Pro), data from run
[41328368604](https://github.com/Parsaka/bilanzwerk/actions/runs/41328368604); not Direct Lake on
Fabric.** Measured on 1 November 2026.

The model is `powerbi/local` (`generate_tmdl.py --local --marts-folder C:\bilanzwerk-marts-2`),
the same measures, relationships and pages as the Direct Lake model, with import partitions
from the run's Parquet marts. A full refresh of all 27 tables (fact_financial_line 31.3 M rows,
fact_kpi 15.3 M rows) took 360 s; afterwards the engine's working set was 2.9 GB and the saved
data cache (`.pbi/cache.abf`) 1.5 GB.

## Method

* The query of each page's main visual was taken from a server trace while the page rendered
  (the text Performance Analyzer's "Copy query" gives), for pages 7 and 11 the visual named below.
* Each query ran three times on a cold cache: `ClearCache` on the database, then the query.
* Server timings from the same trace events DAX Studio uses: **Total** is the duration of
  `QueryEnd`, **SE** the sum of the `VertiPaqScan` durations of that query (no correction for
  parallel scans), **FE** = Total − SE, **SE queries** the number of `VertiPaqScan` events.
  Internal scans and the batch wrapper are not counted.
* Numbers are milliseconds. Only measured values are shown.

## Main visual per page (median of 3 cold runs)

| Page | Visual (main measure) | Total | FE | SE | SE queries |
|---|---|---:|---:|---:|---:|
| 1 Antwort | Karte Working-Capital-Potenzial ([Cash-Potenzial aktuell]) | 128 | 117 | 9 | 5 |
| 2 Unternehmensüberblick | Kopfzeile ([Befund Unternehmen], Flaggen zum letzten Abschluss) | 67 | 56 | 12 | 11 |
| 3 Bilanzanalyse | Passiva nach Gruppe ([Bestand]) | 141 | 126 | 15 | 2 |
| 4 GuV und Margen | Brücke Umsatz bis EBIT ([GuV-Brücke Betrag]) | 429 | 124 | 324 | 7 |
| 5 Cashflow und Working Capital | CCC gegen Sektormedian ([CCC], [CCC Sektor-Median]) | 912 | 892 | 20 | 7 |
| 6 Peer-Benchmark | Streudiagramm ([KPI-Auswahl Wert], [KPI-Auswahl Y Wert]) | 280 | 243 | 35 | 7 |
| 7 Frühwarnsystem | Risikotabelle ([Risiko 12M], Treiber) | 11 801 | 11 765 | 35 | 26 |
| 8 Fallstudien | CCC der Fallstudie gegen Sektormedian | 240 | 229 | 11 | 10 |
| 9 Working-Capital-Potenzial | Brücke nach Sektor ([Cash-Potenzial aktuell]) | 229 | 187 | 42 | 18 |
| 10 Plan-Ist | WAPE je Geschäftsjahr ([Prognosefehler WAPE]) | 514 | 324 | 190 | 3 |
| 11 Datenqualität | Karte Restatement-Quote ([Restatement-Quote]) | 101 | 97 | 4 | 3 |

## Before and after the measure fixes (PR #8)

| Visual | Run 41311161441, first render | After PR #8 (3 cold runs, median) | After report-fixes-2 (3 cold runs, median) |
|---|---:|---:|---:|
| Karte Restatement-Quote (page 11) | 67 449 | 101 | – (unchanged measure) |
| Risikotabelle (page 7) | 22 099 | 16 864 | 11 801 |

The Restatement-Quote now counts `fact_kpi[is_restated]` from dbt instead of comparing first
reported and latest values per company, period and KPI in DAX. The risk table still spends almost
all its time in the formula engine (16.8 s FE, 38 ms SE): it evaluates each company's own latest
as-of date per row of 502 companies. With the fast path for a single company ([Risiko 12M] filters
that company's latest date directly) it went from 16.9 s to 11.8 s, still 11.8 s FE against 35 ms SE.
It is the one visual worth moving further into dbt: an `is_latest_for_company` flag on
fact_risk_score would reduce it to a filter.

Pages 5 and 8 were measured again after the sector median got its bounds (peers with a CCC
between −730 and 730 days, at least five of them): page 5 went from 217 to 912 ms, page 8 from
183 to 240 ms. The filter over the peers costs formula engine time; both stay under a second.

## All runs

The final model (main with PR #8 and report-fixes-2); pages 2, 5, 7 and 8 measured after the last
measure changes, the others before them (their queries do not use the changed measures).

| Page | Run | Total | FE | SE | SE queries | Rows |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 128 | 117 | 11 | 5 | 1 |
| 1 | 2 | 132 | 127 | 5 | 5 | 1 |
| 1 | 3 | 123 | 114 | 9 | 5 | 1 |
| 2 | 1 | 67 | 57 | 10 | 11 | 1 |
| 2 | 2 | 67 | 55 | 12 | 11 | 1 |
| 2 | 3 | 68 | 56 | 12 | 11 | 1 |
| 3 | 1 | 141 | 126 | 15 | 2 | 60 |
| 3 | 2 | 131 | 121 | 10 | 2 | 60 |
| 3 | 3 | 149 | 133 | 16 | 2 | 60 |
| 4 | 1 | 511 | 144 | 367 | 7 | 4 |
| 4 | 2 | 429 | 124 | 305 | 7 | 4 |
| 4 | 3 | 425 | 101 | 324 | 7 | 4 |
| 5 | 1 | 932 | 912 | 20 | 7 | 209 |
| 5 | 2 | 895 | 873 | 22 | 7 | 209 |
| 5 | 3 | 912 | 892 | 20 | 7 | 209 |
| 6 | 1 | 280 | 243 | 37 | 7 | 2 051 |
| 6 | 2 | 257 | 222 | 35 | 7 | 2 051 |
| 6 | 3 | 317 | 285 | 32 | 7 | 2 051 |
| 7 | 1 | 11 963 | 11 928 | 35 | 26 | 502 |
| 7 | 2 | 11 714 | 11 680 | 34 | 26 | 502 |
| 7 | 3 | 11 801 | 11 765 | 36 | 26 | 502 |
| 8 | 1 | 240 | 229 | 11 | 10 | 72 |
| 8 | 2 | 239 | 227 | 12 | 10 | 72 |
| 8 | 3 | 244 | 233 | 11 | 10 | 72 |
| 9 | 1 | 211 | 183 | 28 | 18 | 11 |
| 9 | 2 | 229 | 187 | 42 | 18 | 11 |
| 9 | 3 | 238 | 193 | 45 | 18 | 11 |
| 10 | 1 | 514 | 324 | 190 | 3 | 20 |
| 10 | 2 | 493 | 304 | 189 | 3 | 20 |
| 10 | 3 | 538 | 348 | 190 | 3 | 20 |
| 11 | 1 | 101 | 97 | 4 | 3 | 1 |
| 11 | 2 | 79 | 75 | 4 | 3 | 1 |
| 11 | 3 | 128 | 121 | 7 | 3 | 1 |

Rows: rows returned by the query (the scatter on page 6 returns its sampled points, the risk
table its first 502 rows). Slicers in the measured state: company MICROSOFT CORP (pages 2–5),
fiscal year 2025 (pages 4, 10), sector Dienstleistungen (pages 6, 7, 10), case FirstEnergy
(page 8), language Deutsch.

## Screenshots

`docs/images/powerbi_<nn>_<page>.png`, taken from the same model in Power BI Desktop after the
refresh.
