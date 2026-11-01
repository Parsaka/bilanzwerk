# Fallstudien

Lauf [41282080293](https://github.com/Parsaka/bilanzwerk/actions/runs/41282080293) (Datenstand `c82f84b4f516fbe8`), Dateien `results/analysis/case_*.csv`,
`case_*_events.csv` und `label_audit.csv` auf dem Branch `real-data-results`. Die Fälle wählt
der Code nach einer festen Regel; Texte und Befunde unten sind nach dem Lauf geschrieben, die
Zahlen stammen aus dem Lauf.

## Was die drei Fälle zeigen

1. **Das Label ist so gut wie die Item-Liste von EDGAR.** Zwei der drei umsatzstärksten
   „Insolvenzen“ sind keine Insolvenz des berichtenden Unternehmens: Bei FirstEnergy ist nur
   eine Tochter Schuldner, bei J C Penney trägt eine 8-K ohne Insolvenz das Item 1.03.
   Deshalb liest `bw-analysis label-audit` jetzt jede 8-K hinter dem Label (unten).
2. **Z'' war in allen drei Fällen lange vorher rot.** Die CCC ließ sich in keinem der drei
   Fälle berechnen, weil mindestens eine von DSO, DIO und DPO fehlte. Das ist der Befund aus
   H1 im Kleinen: Die CCC-Flagge scheitert vor allem an der Verfügbarkeit.
3. **Point-in-time sieht man an „bekannt ab“.** Jeder Wert gilt erst ab der Annahme des
   Filings, das ihn zuerst enthielt; bei FirstEnergy kam der vollständige Z''-Wert zum
   31.12.2017 erst nach dem Ereignis, deshalb fehlt dort der Vorlauf im H1-Maß.

## Prüfung aller Labels gegen den Text der 8-K

`analysis/label_audit.py` hat alle 3 609 8-K hinter dem Hauptlabel von EDGAR gelesen (3 609
gelesen), davon 1 914 als erstes Ereignis eines Unternehmens:

| Befund | alle Filings | erstes Ereignis je Unternehmen |
|---|---|---|
| Unternehmen selbst unter den Schuldnern | 2 925 | 1 530 |
| nach Wortlaut nur eine Tochter Schuldner | 250 | 164 |
| Schuldner aus dem Text nicht erkennbar | 310 | 162 |
| kein Item 1.03 im gelesenen Text gefunden | 124 | 58 |

Die Einordnung ist eine Regel auf dem Wortlaut, keine Prüfung durch einen Menschen. Claude hat
eine Zufallsstichprobe gelesen (erstes Ereignis je Unternehmen): von 12 Fällen „nur Tochter“
waren 10 richtig eingeordnet und 2 falsch (dort sind Mutter und Tochter gemeinsam Schuldner);
von 4 Fällen „nicht erkennbar“ waren 3 Bank-Holdings, deren Bank unter FDIC-Verwaltung kam. „Kein
Item 1.03 gefunden“ heißt: nicht in den ersten 400 KB des ersten Dokuments; bei Filings mit
Inline-XBRL kann der Text auch hinter dieser Grenze liegen. Das Label bleibt wie in
[ADR-001](adr/ADR-001-hypotheses.md) vorab festgelegt; die Zeilen stehen mit Textauszug in
`label_audit.csv` zur Prüfung bereit.

Auswahlregel (im Code festgelegt, `analysis/pipeline.py`): Die drei umsatzstärksten Unternehmen (Umsatz TTM in EUR zum letzten erstveröffentlichten Abschluss vor dem Ereignis) mit Insolvenz (8-K Item 1.03) im Testzeitraum und mindestens acht Beobachtungen davor, höchstens eines je Sektor.

## 1. FIRSTENERGY CORP (CIK 1031296, Transport und Versorger)

| | |
|---|---|
| Ereignis im Label | 8-K Item 1.03 vom 05.04.2018 |
| Umsatz TTM vor dem Ereignis | 11,5 Mrd. EUR |
| Vorlauf CCC-Flagge / Z''-Flagge (H1-Messung) | – / – Monate |
| Kennzahl im letzten Quartal vor dem Ereignis berechenbar: CCC / Z'' | nein / nein |
| Vorlauf nur über berechenbare Quartale (Sensitivität): CCC / Z'' | – / 104,0 Monate |

**Die 8-K mit Item 1.03 (EDGAR) und was im Text steht**

| Datum | Filing | Items laut EDGAR | Textprüfung (`label_audit`) |
|---|---|---|---|
| 2018-04-05 | [0001031296-18-000024](https://www.sec.gov/Archives/edgar/data/1031296/000103129618000024/0001031296-18-000024-index.htm) | 1.03,2.01,9.01 | nur eine Tochter ist Schuldner (nach Wortlaut) |

Weitere Ereignisse: 2003-08-15 NT 10-Q; 2020-08-10 NT 10-Q; 2020-11-09 NT 10-Q.

**Befund.** Der Text der 8-K (EDGAR, gelesen am 01.11.2026) nennt als Schuldner FirstEnergy Solutions Corp. mit Töchtern und FirstEnergy Nuclear Operating Company, „each wholly owned subsidiaries of FirstEnergy Corp.“; FirstEnergy Corp. selbst ist nicht unter den Schuldnern, und ihre Abschlüsse laufen in den Daten nach 2018 weiter. Das Label zählt hier also die Insolvenz einer Tochter. Z'' war in allen acht Perioden rot; im H1-Maß fehlt der Vorlauf, weil der Z''-Wert zum 31.12.2017 erst am 23.04.2018 vollständig bekannt war, nach dem Ereignis. Die CCC ließ sich in keiner dieser Perioden berechnen: Von ihren Teilgrößen liegt nur DSO vor, DIO und DPO fehlen.

**Die letzten acht Perioden vor dem Ereignis** (erstveröffentlichte Werte; „rot“ = Flagge des Modells)

| Periodenende | Z'' | Z'' bekannt ab | CCC (Tage) | CCC bekannt ab |
|---|---|---|---|---|
| 30.06.2016 | 0,03 rot | 28.07.2016 | nicht berechenbar | – |
| 30.09.2016 | 0,04 rot | 04.11.2016 | nicht berechenbar | – |
| 31.12.2016 | −2,09 rot | 21.02.2017 | nicht berechenbar | – |
| 31.03.2017 | −2,21 rot | 27.04.2017 | nicht berechenbar | – |
| 30.06.2017 | −1,50 rot | 27.07.2017 | nicht berechenbar | – |
| 30.09.2017 | −1,37 rot | 26.10.2017 | nicht berechenbar | – |
| 31.12.2017 | −0,50 rot | 23.04.2018 | nicht berechenbar | – |
| 31.03.2018 | −0,59 rot | 23.04.2018 | nicht berechenbar | – |

## 2. J C PENNEY CO INC (CIK 1166126, Handel)

| | |
|---|---|
| Ereignis im Label | 8-K Item 1.03 vom 28.01.2014 |
| Umsatz TTM vor dem Ereignis | 9,1 Mrd. EUR |
| Vorlauf CCC-Flagge / Z''-Flagge (H1-Messung) | – / 10,3 Monate |
| Kennzahl im letzten Quartal vor dem Ereignis berechenbar: CCC / Z'' | nein / ja |
| Vorlauf nur über berechenbare Quartale (Sensitivität): CCC / Z'' | – / 10,3 Monate |

**Die 8-K mit Item 1.03 (EDGAR) und was im Text steht**

| Datum | Filing | Items laut EDGAR | Textprüfung (`label_audit`) |
|---|---|---|---|
| 2014-01-28 | [0001166126-14-000005](https://www.sec.gov/Archives/edgar/data/1166126/000116612614000005/0001166126-14-000005-index.htm) | 1.01,1.03,8.01,9.01 | kein Item 1.03 im Text |
| 2020-05-18 | [0001193125-20-144411](https://www.sec.gov/Archives/edgar/data/1166126/000119312520144411/0001193125-20-144411-index.htm) | 1.01,1.03,2.04,3.01,3.03,7.01,8.01,9.01 | das Unternehmen selbst ist Schuldner |
| 2020-12-16 | [0001193125-20-319094](https://www.sec.gov/Archives/edgar/data/1166126/000119312520319094/0001193125-20-319094-index.htm) | 1.03,9.01 | das Unternehmen selbst ist Schuldner |
| 2021-02-01 | [0001193125-21-023867](https://www.sec.gov/Archives/edgar/data/1166126/000119312521023867/0001193125-21-023867-index.htm) | 1.02,1.03,2.01,2.05,3.03,5.02,8.01,9.01 | das Unternehmen selbst ist Schuldner |

Weitere Ereignisse: 2020-05-20 25-NSE; 2021-02-01 15-12B.

**Befund.** Die 8-K vom 28.01.2014 trägt in EDGAR Item 1.03, ihr Text behandelt aber einen geänderten Rechteplan zum Schutz steuerlicher Verlustvorträge (Item 3.03) und Item 1.01; eine Insolvenz kommt nicht vor (EDGAR, gelesen am 01.11.2026). Das Label datiert J C Penney damit sechs Jahre zu früh: Der eigene Chapter-11-Antrag folgte am 15.05.2020 (8-K vom 18.05.2020). Die Z''-Flagge war ab dem Abschluss zum 31.01.2013 rot und blieb es bis zum (falschen) Ereignis. Die CCC war nicht berechenbar: DIO und DPO liegen vor, DSO fehlt.

**Die letzten acht Perioden vor dem Ereignis** (erstveröffentlichte Werte; „rot“ = Flagge des Modells)

| Periodenende | Z'' | Z'' bekannt ab | CCC (Tage) | CCC bekannt ab |
|---|---|---|---|---|
| 31.01.2012 | 2,30 | 27.03.2012 | nicht berechenbar | – |
| 30.04.2012 | 2,03 | 05.06.2012 | nicht berechenbar | – |
| 31.07.2012 | 1,82 | 04.09.2012 | nicht berechenbar | – |
| 31.10.2012 | 1,50 | 04.12.2012 | nicht berechenbar | – |
| 31.01.2013 | 0,47 rot | 20.03.2013 | nicht berechenbar | – |
| 30.04.2013 | −0,43 rot | 11.06.2013 | nicht berechenbar | – |
| 31.07.2013 | −0,08 rot | 10.09.2013 | nicht berechenbar | – |
| 31.10.2013 | −0,05 rot | 05.12.2013 | nicht berechenbar | – |

## 3. IHEARTMEDIA, INC. (CIK 1400891, Technologie und Telekommunikation)

| | |
|---|---|
| Ereignis im Label | 8-K Item 1.03 vom 15.03.2018 |
| Umsatz TTM vor dem Ereignis | 5,5 Mrd. EUR |
| Vorlauf CCC-Flagge / Z''-Flagge (H1-Messung) | – / 70,3 Monate |
| Kennzahl im letzten Quartal vor dem Ereignis berechenbar: CCC / Z'' | nein / ja |
| Vorlauf nur über berechenbare Quartale (Sensitivität): CCC / Z'' | – / 79,3 Monate |

**Die 8-K mit Item 1.03 (EDGAR) und was im Text steht**

| Datum | Filing | Items laut EDGAR | Textprüfung (`label_audit`) |
|---|---|---|---|
| 2018-03-15 | [0001193125-18-083055](https://www.sec.gov/Archives/edgar/data/1400891/000119312518083055/0001193125-18-083055-index.htm) | 1.03,2.02,2.04,7.01,8.01,9.01 | das Unternehmen selbst ist Schuldner |
| 2019-01-28 | [0001193125-19-019100](https://www.sec.gov/Archives/edgar/data/1400891/000119312519019100/0001193125-19-019100-index.htm) | 1.03,7.01,9.01 | das Unternehmen selbst ist Schuldner |

Weitere Ereignisse: 2018-04-03 NT 10-K; 2018-05-16 NT 10-Q; 2019-05-03 15-12G.

**Befund.** Die 8-K nennt iHeartMedia, Inc. und Töchter als Schuldner (Chapter 11 am 14.03.2018); das Label stimmt. Z'' war in jeder der acht Perioden rot, im H1-Maß 70,3 Monate vor dem Ereignis zum ersten Mal dauerhaft. Die CCC war nicht berechenbar: DSO liegt vor, DIO und DPO fehlen.

**Die letzten acht Perioden vor dem Ereignis** (erstveröffentlichte Werte; „rot“ = Flagge des Modells)

| Periodenende | Z'' | Z'' bekannt ab | CCC (Tage) | CCC bekannt ab |
|---|---|---|---|---|
| 31.03.2016 | −2,18 rot | 04.05.2016 | nicht berechenbar | – |
| 30.06.2016 | −2,58 rot | 04.08.2016 | nicht berechenbar | – |
| 30.09.2016 | −2,61 rot | 09.11.2016 | nicht berechenbar | – |
| 31.12.2016 | −2,51 rot | 23.02.2017 | nicht berechenbar | – |
| 31.03.2017 | −3,13 rot | 04.05.2017 | nicht berechenbar | – |
| 30.06.2017 | −3,29 rot | 03.08.2017 | nicht berechenbar | – |
| 30.09.2017 | −3,38 rot | 08.11.2017 | nicht berechenbar | – |
| 31.12.2017 | −11,11 rot | 03.05.2018 | nicht berechenbar | – |

