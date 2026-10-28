# Berichtsseiten / Report pages

Generated from `powerbi/report/pages.yml` by `powerbi/tools/generate_report.py`. Each page answers one
question, printed in its title. Title, language switch and footer are generated; the main visuals
are placed in Power BI Desktop as listed here.

Design rules: one accent colour (#1F5AA6) for the item the title talks about, grey for the rest,
red and green only for risk bands; every chart title states the finding (written after the real-data
run, never before); a footer on each page with data cut-off date and source (measure `Fußzeile`).

| # | Seite | Frage | Question | Main visuals | Measures |
|---|---|---|---|---|---|
| 1 | Antwort | Was haben wir herausgefunden? | What did we find? | Vier Hypothesen-Karten H1–H4: gehalten oder nicht, Kennzahl, 95%-Intervall (Quelle: analysis/answer.json, nicht von Hand)<br>Vorlaufzeit-Diagramm Z'' gegen CCC (Monate vor dem Ereignis, Median und Interquartil)<br>Summe Cash-Potenzial in Mrd. EUR ([Cash-Potenzial]) | `[Cash-Potenzial]`, `[Insolvenzen]`, `[Unternehmen rot]` |
| 2 | Unternehmensüberblick | Wie steht dieses Unternehmen da? | How is this company doing? | KPI-Karten mit Sektorperzentil ([KPI Wert], [Sektorperzentil])<br>10-Jahres-Trendlinien Umsatz, EBIT-Marge, Eigenkapitalquote<br>Risikoband (Ampel) aus [Risiko 12M]<br>Einreichungshistorie (fact_event und Filings) als Zeitleiste | `[KPI Wert]`, `[Sektorperzentil]`, `[Risiko 12M]`, `[Umsatz]`, `[EBIT-Marge]`, `[Eigenkapitalquote]` |
| 3 | Bilanzanalyse | Ist die Bilanz gesund? | Is the balance sheet healthy? | Aktiva- und Passiva-Struktur als gestapelte Balken über die Zeit (dim_line_item Hierarchie)<br>Eigenkapitalquote und Verschuldungsgrad als Linien gegen den Sektormedian | `[Bestand]`, `[Bilanzsumme]`, `[Eigenkapitalquote]`, `[Verschuldungsgrad]` |
| 4 | GuV und Margen | Woher kommt der Gewinn? | Where does profit come from? | Wasserfall Umsatz bis EBIT<br>Margentrends (Brutto, EBIT) gegen den Sektor | `[Umsatz]`, `[COGS]`, `[EBIT]`, `[Bruttomarge]`, `[EBIT-Marge]` |
| 5 | Cashflow und Working Capital | Wo ist Cash gebunden? | Where is cash tied up? | DSO, DIO, DPO, CCC über die Zeit gegen den Sektormedian<br>Cash Conversion (CFO / EBIT) | `[DSO]`, `[DIO]`, `[DPO]`, `[CCC]`, `[CCC Sektor-Median]`, `[Cash Conversion (CFO / EBIT)]` |
| 6 | Peer-Benchmark | Wie stehen wir im Vergleich da? | How do we compare? | Streudiagramm zweier frei wählbarer Kennzahlen (Feldparameter KPI-Auswahl, zweimal)<br>Sektorperzentile als Balken<br>Rangliste (Tabelle) mit Sektorperzentil | `[KPI Wert]`, `[Sektorperzentil]` |
| 7 | Frühwarnsystem | Welche Unternehmen brauchen jetzt Aufmerksamkeit? | Which companies need attention now? | Ampeltabelle der Risikobänder (rot/gelb/grün nur hier)<br>Treiber je Unternehmen aus SHAP (fact_risk_score.top_3_drivers, per OLS für Reporting verborgen)<br>Veränderung zum Vorquartal | `[Risiko 12M]`, `[Unternehmen rot]`, `[Risiko Veränderung zum Vorquartal]`, `[Rote Flaggen]` |
| 8 | Fallstudien | Wie sah die Warnung vor echten Insolvenzen aus? | What did the warning look like before real bankruptcies? | Drei Unternehmens-Zeitleisten mit Kennzahlen, roten Flaggen und markiertem Ereignis (Auswahl nach dem Echtdatenlauf, bw-analysis case) | `[Z'' Score]`, `[CCC]`, `[Rote Flaggen]`, `[Risiko 12M]`, `[Insolvenzen]` |
| 9 | Working-Capital-Potenzial | Wie viel Cash ließe sich freisetzen? | How much cash could be freed? | Brücke nach Sektor in Mrd. EUR<br>Top 20 Unternehmen<br>Stretch-Szenario (oberes Quartil statt Median) | `[Cash-Potenzial]`, `[Cash-Potenzial Stretch]` |
| 10 | Plan-Ist | Wie weit lag das Ist neben dem Plan? | How far did actuals miss plan? | Abweichung nach Sektor und Unternehmen, absolut und in % (Berechnungsgruppe Szenario)<br>Prognosefehler (MAPE) | `[Umsatz]`, `[Prognosefehler MAPE]` |
| 11 | Datenqualität | Können wir den Zahlen trauen? | Can we trust the numbers? | Scorecard je Regel und Lauf (fact_data_quality)<br>LEI-Match-Quote, Restatement-Quote<br>Stewardship-Warteschlange<br>Service Levels aus docs/runbook.md: Frische 24 h, Bilanzprüfung ≥ 98 %, Refresh-Erfolg 99 % | `[DQ Pass-Rate]`, `[Regeln verletzt]`, `[LEI-Match-Quote]`, `[Restatement-Quote]`, `[Offene Stewardship-Fälle]` |

## Status

Pages with a build note (`bauplan` visual) still need their main visuals. Screenshots of all 11 pages
go to `docs/img/report/` once the report runs on real data.
