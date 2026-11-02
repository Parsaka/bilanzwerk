# Report performance on a local PC

**Import mode in Power BI Desktop 2.156.951.0 on a local PC (Intel Core i5-1135G7, 4 cores /
8 threads, 15.7 GB RAM, Windows 11 Pro), data from run
[41374506654](https://github.com/Parsaka/bilanzwerk/actions/runs/41374506654); not Direct Lake on
Fabric.** Measured on 2 November 2026. The earlier run 41328368604 (1 November) is kept at the end.

The model is `powerbi/local` (`generate_tmdl.py --local --marts-folder C:\bilanzwerk-marts-3`),
the same measures, relationships and pages as the Direct Lake model, with import partitions
from the run's Parquet marts. A full refresh of all 27 tables (fact_financial_line 31.3 M rows,
fact_kpi 15.3 M rows) took 674 s, and 874 s for the second refresh after the model change below
(same data, other programs running on the PC); afterwards the engine's working set was 3.7 to
3.9 GB.

## Method

* The query of each page's main visual was taken from a server trace while the page rendered
  (the text Performance Analyzer's "Copy query" gives), for pages 7 and 11 the visual named below.
  The visuals are the same as in the earlier run; only the risk table on page 7 sends a different
  query now (see below).
* Each query ran three times on a cold cache: `ClearCache` on the database, then the query.
* Server timings from the same trace events DAX Studio uses: **Total** is the duration of
  `QueryEnd`, **SE** the sum of the `VertiPaqScan` durations of that query (no correction for
  parallel scans), **FE** = Total − SE, **SE queries** the number of `VertiPaqScan` events.
  Internal scans and the batch wrapper are not counted.
* Numbers are milliseconds. Only measured values are shown.

## Main visual per page (median of 3 cold runs)

| Page | Visual (main measure) | Total | FE | SE | SE queries |
|---|---|---:|---:|---:|---:|
| 1 Antwort | Karte Working-Capital-Potenzial ([Cash-Potenzial aktuell]) | 76 | 70 | 6 | 5 |
| 2 Unternehmensüberblick | Kopfzeile ([Befund Unternehmen], Flaggen zum letzten Abschluss) | 128 | 110 | 18 | 9 |
| 3 Bilanzanalyse | Passiva nach Gruppe ([Bestand]) | 161 | 106 | 55 | 7 |
| 4 GuV und Margen | Brücke Umsatz bis EBIT ([GuV-Brücke Betrag]) | 421 | 102 | 305 | 7 |
| 5 Cashflow und Working Capital | CCC gegen Sektormedian ([CCC], [CCC Sektor-Median]) | 1 928 | 1 897 | 33 | 7 |
| 6 Peer-Benchmark | Streudiagramm ([KPI-Auswahl Wert], [KPI-Auswahl Y Wert]) | 279 | 241 | 30 | 7 |
| 7 Frühwarnsystem | Risikotabelle ([Risiko 12M], [Rote Flaggen Risikotabelle], [Stärkste Treiber]) | 333 | 229 | 109 | 7 |
| 8 Fallstudien | CCC der Fallstudie gegen Sektormedian | 547 | 518 | 29 | 13 |
| 9 Working-Capital-Potenzial | Brücke nach Sektor ([Cash-Potenzial aktuell]) | 190 | 150 | 40 | 18 |
| 10 Plan-Ist | WAPE je Geschäftsjahr ([Prognosefehler WAPE]) | 527 | 332 | 208 | 3 |
| 11 Datenqualität | Karte Restatement-Quote ([Restatement-Quote]) | 104 | 99 | 5 | 3 |

These are the timings of the final model. An hour earlier, in the first Desktop session on the
same data and before the page 7 change, the same queries ran in about half the time (for
example page 5 955 ms, page 8 240 ms, page 11 42 ms, close to the earlier run). The second
session was slower on every page; the CPU load from other programs was 13 to 22 %, the exact
cause was not found. Compare pages within one set, and before/after within one session (below).

## Before and after

| Visual | Run 41311161441, first render | After PR #8 | After report-fixes-2 | `is_latest_for_company` in dbt (run 41374506654) | Drivers as a measure (run 41374506654) |
|---|---:|---:|---:|---:|---:|
| Karte Restatement-Quote (page 11) | 67 449 | 101 | – (unchanged measure) | 42 | 104 |
| Risikotabelle (page 7) | 22 099 | 16 864 | 11 801 | 7 504 | 333 |

Medians of 3 cold runs except the first column. The last two columns come from the two Desktop
sessions described above. In the same (second) session the risk table's query before the change
took 15 524 ms (FE 15 501, SE 23) and after it 298 ms (FE 198, SE 104), about 50 times faster.

`[Risiko 12M]` and `[Unternehmen rot]` filter `fact_risk_score[is_latest_for_company] = 1`
(dbt) instead of finding each company's latest as-of date in DAX. That alone brought the risk
table from 11.8 s to 7.5 s, still almost all formula engine. The rest came from the table's
columns: it grouped by the column `fact_risk_score[top_3_drivers]` next to `[Rote Flaggen]` from
`fact_kpi`, which has no relationship to that column, so the engine paired every company with
every driver text (the same query without the TOPN window returned 9.4 million rows in 160 s)
and cut the result to 501 rows afterwards. Now the drivers are the measure `[Stärkste Treiber]`
(champion model, latest as-of date) and the flags are `[Rote Flaggen Risikotabelle]` (latest
filing, only for companies with a risk score), so the table groups by company and sector only.
The flag count also changed meaning: before, it summed the flags of all periods (values up to
380); now it counts those of the latest filing, as the header on page 2 does. The test
`test_risk_table_groups_only_by_dimensions` keeps fact columns out of that table.

## All runs

The final model: the same 11 queries, three cold runs each, in one go.

| Page | Run | Total | FE | SE | SE queries | Rows |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 75 | 68 | 7 | 5 | 1 |
| 1 | 2 | 76 | 70 | 6 | 5 | 1 |
| 1 | 3 | 95 | 91 | 4 | 5 | 1 |
| 2 | 1 | 128 | 113 | 15 | 9 | 1 |
| 2 | 2 | 98 | 80 | 18 | 9 | 1 |
| 2 | 3 | 133 | 110 | 23 | 9 | 1 |
| 3 | 1 | 190 | 130 | 60 | 7 | 60 |
| 3 | 2 | 161 | 106 | 55 | 7 | 60 |
| 3 | 3 | 150 | 97 | 53 | 7 | 60 |
| 4 | 1 | 421 | 93 | 328 | 7 | 4 |
| 4 | 2 | 386 | 102 | 284 | 7 | 4 |
| 4 | 3 | 425 | 120 | 305 | 7 | 4 |
| 5 | 1 | 1 922 | 1 889 | 33 | 7 | 209 |
| 5 | 2 | 2 024 | 1 974 | 50 | 7 | 209 |
| 5 | 3 | 1 928 | 1 897 | 31 | 7 | 209 |
| 6 | 1 | 279 | 241 | 38 | 7 | 2 050 |
| 6 | 2 | 295 | 266 | 29 | 7 | 2 050 |
| 6 | 3 | 257 | 227 | 30 | 7 | 2 050 |
| 7 | 1 | 333 | 229 | 104 | 7 | 502 |
| 7 | 2 | 423 | 294 | 129 | 7 | 502 |
| 7 | 3 | 323 | 214 | 109 | 7 | 502 |
| 8 | 1 | 420 | 397 | 23 | 13 | 72 |
| 8 | 2 | 547 | 518 | 29 | 13 | 72 |
| 8 | 3 | 602 | 570 | 32 | 13 | 72 |
| 9 | 1 | 191 | 150 | 41 | 18 | 11 |
| 9 | 2 | 165 | 130 | 35 | 18 | 11 |
| 9 | 3 | 190 | 150 | 40 | 18 | 11 |
| 10 | 1 | 579 | 362 | 217 | 3 | 20 |
| 10 | 2 | 493 | 285 | 208 | 3 | 20 |
| 10 | 3 | 527 | 332 | 195 | 3 | 20 |
| 11 | 1 | 104 | 99 | 5 | 3 | 1 |
| 11 | 2 | 91 | 84 | 7 | 3 | 1 |
| 11 | 3 | 108 | 103 | 5 | 3 | 1 |

Rows: rows returned by the query (the scatter on page 6 returns its sampled points, the risk
table its first 502 rows). Slicers in the measured state: company MICROSOFT CORP (pages 2–5),
fiscal year 2025 (pages 4, 10), sector Dienstleistungen (pages 6, 7, 10), case FirstEnergy
(page 8), language Deutsch.

## Screenshots

`docs/images/powerbi_<nn>_<page>.png`, taken from the same model in Power BI Desktop after the
refresh.

## Earlier run 41328368604 (1 November 2026)

Same PC and method; full refresh 360 s, working set 2.9 GB, saved data cache 1.5 GB.

### Main visual per page (median of 3 cold runs)

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

### Before and after the measure fixes (PR #8)

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

### All runs

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
