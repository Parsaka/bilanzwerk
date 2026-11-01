# Management Summary

Stand: Lauf auf echten Daten vom 01.11.2026
([Actions 41282080293](https://github.com/Parsaka/bilanzwerk/actions/runs/41282080293), Datenstand `c82f84b4f516fbe8`; Zahlen in `results/` auf dem Branch
`real-data-results`). Keine Zahl hier stammt aus einer anderen Quelle.

## Die Frage

Welche veröffentlichten Kennzahlen warnen am frühesten und zuverlässigsten, dass ein
börsennotiertes Unternehmen innerhalb von 12 Monaten insolvent wird, und warnt das Working
Capital früher als der Altman Z''-Score? Und wie viel Liquidität könnte jeder Sektor
freisetzen, wenn seine Unternehmen DSO, DIO und DPO auf den Sektormedian bringen?

## Die Antwort in vier Zeilen

| | Ergebnis | Zahl | 95%-KI |
|---|---|---|---|
| H1 CCC warnt früher als Z'' | nicht bestätigt | Median 0,0 gegen 12,7 Monate, Differenz −12,7 | −14,9 bis −11,1 |
| H2 Z'' + Working Capital schlägt Z'' (PR-AUC) | nicht bestätigt | −0,002 | −0,004 bis −0,001 |
| H3 sektorrelativ schlägt absolut (PR-AUC) | bestätigt | +0,004 | +0,002 bis +0,006 |
| H4 Working-Capital-Potenzial | bestätigt | 1 309 Mrd. EUR, davon Technologie und Telekommunikation 338 | – |

## Was das für eine Kreditabteilung heißt

- Z'': Bei 68 % der 645 späteren Insolvenzen mit Kennzahlen war die Z''-Flagge bis zum
  Ereignis rot, im Median 12,7 Monate vorher (nur geflaggte: 23,2 Monate).
- Die CCC-Flagge in ihrer jetzigen Form (oberes Sektorquintil und steigend) war nur bei
  4 % rot. Wo sie kam, kam sie im Median 4,7 Monate vorher. Im letzten Quartal vor dem
  Ereignis ließ sich die CCC nur bei 40 % der Unternehmen berechnen (Z'': 75 %); zählt man
  nur berechenbare Quartale, ist die Differenz −21,1 Monate (95%-KI −25,5 bis −17,9).
- Das beste Modell ist M3 (LightGBM auf allen Kennzahlen): PR-AUC 0,053 gegen 0,019 für Z''
  allein (M1); in den riskantesten 5 % der Unternehmen findet es 34 % der Insolvenzen
  (M1: 10 %). Bei einer Ereignisrate unter 1 % ist auch das ein Ranking-Werkzeug, kein Urteil
  über einzelne Unternehmen.
- Kennzahlen relativ zum Sektor: H3 bestätigt; Working Capital zusätzlich zu Z'': H2 nicht bestätigt.
- Die Berichte zeigen M3 (Champion-Regel aus ADR-007: PR-AUC M3 minus M2 = +0,037, 95%-KI
  +0,027 bis +0,047); die Treiber je Unternehmen kommen aus SHAP.

## Was das für Controller heißt

Working-Capital-Potenzial bis zum Sektormedian (letztes Geschäftsjahr je Unternehmen,
Nicht-Finanzunternehmen mit Sektorzuordnung, mindestens 5 Vergleichsunternehmen):

| Sektor | Mrd. EUR | Unternehmen |
|---|---|---|
| Technologie und Telekommunikation | 337,6 | 1 734 |
| Handel | 290,9 | 663 |
| Industrie und Bau | 137,5 | 752 |
| Gesundheit | 129,9 | 966 |
| Konsumgüter | 88,2 | 466 |
| Grundstoffe und Chemie | 86,1 | 457 |
| Energie | 77,0 | 133 |
| Transport und Versorger | 68,6 | 272 |
| Dienstleistungen | 61,3 | 726 |
| Rohstoffe und Landwirtschaft | 31,5 | 211 |
| **Summe** | **1 308,6** | **6 380** |

Bis zum besten Quartil (Stretch-Ziel) wären es 2 940 Mrd. EUR. Die Tableau-Arbeitsmappe aus
demselben Lauf zeigt 1 309 Mrd. EUR über 6 380 Unternehmen (Prüfung gegen H4 im Lauf).

## Grenzen

- Ereignis ist 8-K Item 1.03 (1 726 Insolvenzen mit Label); Delistings ohne Insolvenz zählen
  nicht als Ereignis. Unternehmen, die ohne Ereignis verschwinden, werden zensiert.
- Das Label ist so gut wie die Item-Liste von EDGAR. Der Abgleich mit dem Text der 8-Ks
  ([Fallstudien](../case-studies.md), `results/analysis/label_audit.json`) fand 124 Filings
  ohne Item 1.03 im Text und 250 Filings, in denen nach dem Wortlaut nur eine Tochter
  insolvent ist, von 3 609 gelesenen. Das Label bleibt wie in ADR-001 festgelegt.
- Point-in-time: Das Modell sieht nur erstveröffentlichte Werte, jede Kennzahl ab dem
  Annahmedatum ihrer eigenen Eingangsgrößen.
- Datenstand: SEC FSDS bis 2026q3, Labels bis Ende 2025 (spätere Fenster sind unvollständig
  und zensiert).
