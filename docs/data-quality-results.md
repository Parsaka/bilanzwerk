# Datenqualität im Lauf auf echten Daten

Lauf [41282080293](https://github.com/Parsaka/bilanzwerk/actions/runs/41282080293), `results/data_quality.csv` auf dem Branch `real-data-results`
(`marts.fact_data_quality`, letzter Stand je Regel). Regeln und Ziele:
[ADR-010](adr/ADR-010-data-quality-and-contracts.md), `dbt/models/marts/facts/fact_data_quality.sql`.

| Regel | geprüft | bestanden | Ziel | Status |
|---|---|---|---|---|
| `COMPL_ANNUAL_CORE` | 88 896 | 83,0 % | 95,0 % | fail |
| `COMPL_GOLDEN_RECORD` | 991 164 | 100,0 % | 100,0 % | pass |
| `CONS_BALANCE_CHECK` | 426 270 | 99,9 % | 98,0 % | pass |
| `CONS_CASH_BS_CF` | 460 360 | 91,0 % | 90,0 % | pass |
| `CONS_QUARTERS_SUM_TO_YEAR` | 27 539 | 89,9 % | 98,0 % | fail |
| `MDM_LEI_MATCH_RATE` | 16 891 | 22,4 % | – | info |
| `SCALE_OUTLIER_TOTAL_ASSETS` | 389 780 | 99,9 % | 99,9 % | pass |
| `TIMELY_SEC_QUARTER` | 1 | 100,0 % | 100,0 % | pass |
| `UNIQ_FACT_FINANCIAL_LINE` | 31 260 160 | 100,0 % | 100,0 % | pass |
| `UNIQ_GOLDEN_PER_LEI` | 6 053 | 99,5 % | 99,0 % | pass |
| `VALID_EQUITY_RATIO_BOUNDS` | 821 339 | 93,4 % | 99,0 % | fail |
| `VALID_ISO_CURRENCY` | 31 260 160 | 100,0 % | 100,0 % | pass |

## Was die verfehlten Ziele bedeuten

`CONS_CASH_BS_CF` (Kassenbestand Bilanz gegen Kapitalflussrechnung) erreicht mit 91,0 % sein Ziel
von 90 % knapp.

Die Anteile stammen aus dem Lauf; die genannten Ursachen sind die Muster, für die diese Regeln
gebaut sind, und **nicht** je Fall ausgezählt.

- **`COMPL_ANNUAL_CORE`** (17,0 % der Jahresabschlüsse von Nicht-Finanzunternehmen): Umsatz,
  Bilanzsumme oder Schulden fehlen nach dem Mapping, etwa weil ein Filer eigene Tags nutzt.
  Die betroffenen Kennzahlen bleiben leer, sie werden nicht geschätzt.
- **`CONS_QUARTERS_SUM_TO_YEAR`** (10,1 % der Jahre): Die vier Quartalsumsätze ergeben nicht
  den Jahresumsatz ± 0,5 %, zum Beispiel bei 52/53-Wochen-Jahren oder nachträglich angepassten
  Quartalen. Das Modell nutzt TTM aus dem Jahreswert, wo es einen gibt.
- **`VALID_EQUITY_RATIO_BOUNDS`** (6,6 % der Perioden): Eigenkapitalquote außerhalb der
  Grenzen der Regel, typisch für Gesellschaften mit sehr kleiner Bilanzsumme und großem
  Fehlbetrag. Die Werte werden nicht korrigiert; in die Modelle gehen sie als Perzentil ein.

## Zwei Regeln, die leicht verwechselt werden

- **`UNIQ_GOLDEN_PER_LEI`** zählt Golden Records mit LEI, die mehr als eine SEC-CIK bündeln:
  29 von 6 053. Das ist entweder ein Unternehmen, das unter alter und neuer CIK
  berichtet, oder eine falsche Zusammenführung; die Fälle stehen in `dim_company` mit
  `n_ciks > 1` zur Prüfung bereit.
- **Doppelte Golden Records** (eine LEI auf mehreren Golden Records) gab es 0
  (`results/mdm_metrics.json`).
- **`MDM_LEI_MATCH_RATE`** ist eine Kennzahl ohne Ziel: Anteil der SEC-Filer mit Perioden, die
  eine LEI haben. Ein SEC-Filer ohne Treffer hat keine LEI, wurde vom Abgleich verfehlt oder steht in der
  Stewardship-Queue (1 626 offene Fälle). Die Karte „LEI-Match-Quote“ im Power-BI-Bericht
  zählt anders: aktuelle Zeilen von `dim_company` mit CIK (Lauf 41328368604: 3 749 von 17 147,
  21,9 %), die Regel zählt SEC-Filer mit Perioden auf `bv_company_golden`.
