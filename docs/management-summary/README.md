# Management Summary

Stand: Lauf auf echten Daten vom 28.10.2026
([Actions 40684230866](https://github.com/Parsaka/bilanzwerk/actions/runs/40684230866);
Zahlen in `results/analysis/` auf dem Branch `real-data-results`). Keine Zahl hier stammt
aus einer anderen Quelle.

## Die Frage

Welche veröffentlichten Kennzahlen warnen am frühesten und zuverlässigsten, dass ein
börsennotiertes Unternehmen innerhalb von 12 Monaten insolvent wird, und warnt das Working
Capital früher als der Altman Z''-Score? Und wie viel Liquidität könnte jeder Sektor
freisetzen, wenn seine Unternehmen DSO, DIO und DPO auf den Sektormedian bringen?

## Die Antwort in vier Zeilen

| | Ergebnis | Zahl | 95%-KI |
|---|---|---|---|
| H1 CCC warnt früher als Z'' | nicht bestätigt | Median 0,0 gegen 6,0 Monate, Differenz −6,0 | −7,4 bis −4,6 |
| H2 Z'' + Working Capital schlägt Z'' (PR-AUC) | nicht bestätigt | −0,004 | −0,007 bis −0,001 |
| H3 sektorrelativ schlägt absolut (PR-AUC) | bestätigt | +0,009 | +0,006 bis +0,012 |
| H4 Working-Capital-Potenzial | bestätigt | 1 295 Mrd. EUR, davon Technologie und Telekommunikation 328 | – |

## Was das für eine Kreditabteilung heißt

- Z'' bleibt auf der Watchlist: Bei 63 % der 630 späteren Insolvenzen mit Kennzahlen war die
  Z''-Flagge vorher rot, im Median 6,0 Monate vorher (nur geflaggte: 11,4 Monate).
- Die CCC-Flagge in ihrer jetzigen Form (oberes Sektorquintil und steigend) war nur bei 4 %
  rot. Wo sie kam, kam sie im Median 4,7 Monate vorher.
- Das beste Modell ist M3 (LightGBM auf allen Kennzahlen): PR-AUC 0,066 gegen 0,030 für Z''
  allein (M1); in den riskantesten 5 % der Unternehmen findet es 36 % der Insolvenzen
  (M1: 22 %). Bei einer Ereignisrate unter 1 % ist auch das noch ein Ranking-Werkzeug, kein
  Urteil über einzelne Unternehmen.
- Kennzahlen relativ zum Sektor helfen (H3), das Working Capital zusätzlich zu Z'' nicht (H2).
- Die Berichte zeigen deshalb M3 (Champion-Regel aus ADR-007: PR-AUC M3 minus M2 = +0,040,
  95%-KI +0,028 bis +0,055); die Treiber je Unternehmen kommen aus SHAP.

## Was das für Controller heißt

Working-Capital-Potenzial bis zum Sektormedian (letztes Geschäftsjahr je Unternehmen,
Nicht-Finanzunternehmen mit Sektorzuordnung, mindestens 5 Vergleichsunternehmen):

| Sektor | Mrd. EUR | Unternehmen |
|---|---|---|
| Technologie und Telekommunikation | 327,7 | 1 728 |
| Handel | 290,4 | 661 |
| Industrie und Bau | 136,8 | 746 |
| Gesundheit | 129,9 | 964 |
| Konsumgüter | 88,1 | 464 |
| Grundstoffe und Chemie | 85,8 | 454 |
| Energie | 76,9 | 132 |
| Transport und Versorger | 67,0 | 265 |
| Dienstleistungen | 61,1 | 721 |
| Rohstoffe und Landwirtschaft | 31,5 | 211 |
| **Summe** | **1 295,3** | |

Bis zum besten Quartil (Stretch-Ziel) wären es 2 911 Mrd. EUR.

## Grenzen

- Ereignis ist 8-K Item 1.03 (1 661 Insolvenzen mit Label); Delistings ohne Insolvenz zählen
  nicht als Ereignis. Unternehmen, die ohne Ereignis verschwinden, werden zensiert.
- Point-in-time: Das Modell sieht nur erstveröffentlichte Werte zum Annahmedatum.
- Die Ursache der seltenen CCC-Flaggen (fehlende Teilgrößen oder echtes schwaches Signal) ist
  noch nicht ausgewertet.
- Datenstand: SEC FSDS bis 2026q3, Labels bis Ende 2025 (spätere Fenster sind unvollständig
  und zensiert).
