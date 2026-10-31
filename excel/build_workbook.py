"""Build the layout of the Excel management report (excel/Bilanzwerk_Monatsbericht.xlsx).

  uv run python excel/build_workbook.py

This writes everything that lives in cells: the one-page Management Cockpit with CUBE formulas
(CUBEELEMENT/CUBEMEMBER, CUBEWERT/CUBEVALUE; Excel stores the English names and shows the
German ones), the XVERWEIS/XLOOKUP lookups from the company input to the golden record, the
print setup and the sheets that Power Query and the PivotTable fill.

Three parts can only be created by Excel itself: the connection to the semantic model
(Analyze in Excel), the Power Query queries with their tables, and the PivotTable with slicers.
excel/finalize_workbook.ps1 adds them with Excel automation on Windows, imports the VBA module
excel/modRefreshAndExport.bas and saves the result as Bilanzwerk_Monatsbericht.xlsm.

KPI rows and their German names come from the dbt seed kpi_definitions.csv, so the cockpit uses
the same glossary as the model.
"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "excel" / "Bilanzwerk_Monatsbericht.xlsx"
SEED = ROOT / "dbt" / "seeds" / "kpi_definitions.csv"

CONNECTION = "Bilanzwerk"  # name finalize_workbook.ps1 gives the Analyze-in-Excel connection
ACCENT, GREY, DARK, LIGHT = "1F5AA6", "8C8C8C", "262626", "F2F2F2"
RED, GREEN, AMBER = "C62828", "2E7D32", "F2B705"

# Amounts: measure, kind (flow is summed over the fiscal year, stock is the year-end balance).
AMOUNTS = [
    ("Umsatz", "Umsatz"),
    ("EBIT", "EBIT"),
    ("Jahresergebnis", "Jahresergebnis"),
    ("Operativer Cashflow", "Operativer Cashflow"),
    ("Bilanzsumme", "Bilanzsumme"),
    ("Eigenkapital", "Eigenkapital"),
    ("Liquide Mittel", "Liquide Mittel"),
]
# KPI rows with their number format (shares as %, days as whole numbers, multiples with decimals).
KPIS = {
    "EQUITY_RATIO": "0.0%",
    "EBIT_MARGIN": "0.0%",
    "GROSS_MARGIN": "0.0%",
    "DSO": "0",
    "DIO": "0",
    "DPO": "0",
    "CCC": "0",
    "CURRENT_RATIO": "0.00",
    "DEBT_EBITDA": "0.00",
    "ZPP": "0.00",
}
ZPP_MEASURE = "Z'' Score"

# Golden record columns, in the order the Power Query "Stammdaten" loads them (A:I).
MASTER_COLUMNS = [
    "company_name",
    "company_id",
    "lei",
    "cik",
    "sector_de",
    "country_code",
    "hq_city",
    "company_status",
    "match_source",
]
RISK_COLUMNS = ["company_name", "sector_de", "as_of_date", "probability_12m", "risk_band", "top_3_drivers"]

thin = Side(style="thin", color="D9D9D9")
HEADER = Font(name="Segoe UI Semibold", size=10, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
BODY = Font(name="Segoe UI", size=10, color=DARK)
NOTE = Font(name="Segoe UI", size=8, color=GREY)
INPUT_FILL = PatternFill("solid", fgColor="FFF8E1")


def kpi_names() -> dict[str, str]:
    with SEED.open(encoding="utf-8") as fh:
        return {r["kpi_code"]: r["name_de"] for r in csv.DictReader(fh)}


def cube_value(measure: str, *members: str) -> str:
    args = ",".join(["BW_Verbindung", f'"[Measures].[{measure}]"', *members])
    return f"CUBEVALUE({args})"


def header_row(ws, row: int, labels: list[str], start_col: int = 2) -> None:
    for i, label in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=label)
        c.font, c.fill = HEADER, HEADER_FILL
        c.alignment = Alignment(horizontal="left" if i == 0 else "right", vertical="center")


def build_cockpit(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Cockpit"
    ws.sheet_view.showGridLines = False
    widths = {"A": 2, "B": 34, "C": 15, "D": 15, "E": 12, "F": 16, "G": 13, "H": 2, "I": 2, "J": 40, "K": 40}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    ws["B1"] = "Management Cockpit"
    ws["B1"].font = Font(name="Segoe UI Semibold", size=18, color=DARK)
    ws["B2"] = '="Geschäftsjahr "&C4&" · "&C3'
    ws["B2"].font = Font(name="Segoe UI", size=11, color=ACCENT)

    # Inputs and golden-record lookups (XVERWEIS/XLOOKUP on the Stammdaten sheet, columns A:I).
    labels = [
        ("Unternehmen", None),
        ("Geschäftsjahr", None),
        ("Unternehmens-ID", "B"),
        ("LEI", "C"),
        ("CIK", "D"),
        ("Sektor", "E"),
        ("Land", "F"),
        ("Status", "H"),
    ]
    for i, (label, col) in enumerate(labels, start=3):
        ws.cell(row=i, column=2, value=label).font = BODY
        cell = ws.cell(row=i, column=3)
        if col is None:
            cell.fill = INPUT_FILL
        else:
            cell.value = f'=_xlfn.XLOOKUP($C$3,Stammdaten!$A:$A,Stammdaten!${col}:${col},"nicht gefunden")'
        cell.font = BODY
        cell.alignment = Alignment(horizontal="left")
    ws["C3"] = "Apple Inc."
    ws["C4"] = "=YEAR(TODAY())-1"
    validation = DataValidation(
        type="list",
        formula1="Stammdaten!$A$2:$A$100000",
        allow_blank=False,
        showErrorMessage=True,
        errorTitle="Unternehmen",
        error="Bitte ein Unternehmen aus den Stammdaten wählen.",
    )
    ws.add_data_validation(validation)
    validation.add("C3")

    # Hidden helper column J/K: the cube members the values slice by.
    members = {
        "J3": '=CUBEMEMBER(BW_Verbindung,"[dim_company].[company_id].&["&$C$5&"]",$C$3)',
        "J4": '=CUBEMEMBER(BW_Verbindung,"[dim_period].[fiscal_year].&["&$C$4&"]","GJ "&$C$4)',
        "J5": '=CUBEMEMBER(BW_Verbindung,"[dim_period].[fiscal_year].&["&($C$4-1)&"]","GJ "&($C$4-1))',
        "J6": '=CUBEMEMBER(BW_Verbindung,"[dim_period].[is_fiscal_year_end].&[1]","Geschäftsjahresende")',
        "J7": '=CUBEMEMBER(BW_Verbindung,"[dim_scenario].[scenario_code].&[PLAN]","Plan")',
        "J8": '=CUBEMEMBER(BW_Verbindung,"[dim_scenario].[scenario_code].&[IST]","Ist")',
    }
    for ref, formula in members.items():
        ws[ref] = formula
        ws[ref].font = NOTE

    # Block 1: amounts in EUR million.
    r = 13
    ws.cell(row=r - 1, column=2, value="Größen in Mio. EUR").font = Font(name="Segoe UI Semibold", size=11)
    header_row(ws, r, ["Position", "GJ", "Vorjahr", "Δ %", "Plan GJ", "Plan-Ist %"])
    for i, (label, measure) in enumerate(AMOUNTS, start=r + 1):
        ws.cell(row=i, column=2, value=label)
        ws.cell(row=i, column=3, value=f'=IFERROR({cube_value(measure, "$J$3", "$J$4", "$J$8")}/10^6,"–")')
        ws.cell(row=i, column=4, value=f'=IFERROR({cube_value(measure, "$J$3", "$J$5", "$J$8")}/10^6,"–")')
        ws.cell(row=i, column=5, value=f'=IF(AND(ISNUMBER(C{i}),ISNUMBER(D{i}),D{i}<>0),(C{i}-D{i})/ABS(D{i}),"–")')
        if measure == "Umsatz":  # plan exists for revenue only (int_revenue_plan)
            ws.cell(row=i, column=6, value=f'=IFERROR({cube_value(measure, "$J$3", "$J$4", "$J$7")}/10^6,"–")')
            ws.cell(row=i, column=7, value=f'=IF(AND(ISNUMBER(C{i}),ISNUMBER(F{i}),F{i}<>0),(C{i}-F{i})/ABS(F{i}),"–")')
        else:
            ws.cell(row=i, column=6, value="")
            ws.cell(row=i, column=7, value="")
        for col in range(2, 8):
            c = ws.cell(row=i, column=col)
            c.font, c.border = BODY, Border(bottom=thin)
            c.number_format = "0.0%" if col in (5, 7) else "#,##0.0"
            if col > 2:
                c.alignment = Alignment(horizontal="right")
    last_amount = r + len(AMOUNTS)

    # Block 2: KPIs at fiscal year end with sector percentile and red flag.
    names = kpi_names()
    r = last_amount + 3
    ws.cell(row=r - 1, column=2, value="Kennzahlen zum Geschäftsjahresende").font = Font(
        name="Segoe UI Semibold", size=11
    )
    header_row(ws, r, ["Kennzahl", "GJ", "Vorjahr", "Δ", "Sektorperzentil", "Rote Flagge"])
    for i, (code, fmt) in enumerate(KPIS.items(), start=r + 1):
        name = names[code]
        ws.cell(
            row=i, column=11, value=f'=CUBEMEMBER(BW_Verbindung,"[dim_kpi].[kpi_code].&[{code}]","{name}")'
        ).font = NOTE
        ws.cell(row=i, column=2, value=name)
        ws.cell(row=i, column=3, value=f'=IFERROR({cube_value("KPI Wert", "$J$3", "$J$4", "$J$6", f"$K{i}")},"–")')
        ws.cell(row=i, column=4, value=f'=IFERROR({cube_value("KPI Wert", "$J$3", "$J$5", "$J$6", f"$K{i}")},"–")')
        ws.cell(row=i, column=5, value=f'=IF(AND(ISNUMBER(C{i}),ISNUMBER(D{i})),C{i}-D{i},"–")')
        ws.cell(
            row=i, column=6, value=f'=IFERROR({cube_value("Sektorperzentil", "$J$3", "$J$4", "$J$6", f"$K{i}")},"–")'
        )
        ws.cell(
            row=i,
            column=7,
            value=f'=IFERROR(IF({cube_value("Rote Flaggen", "$J$3", "$J$4", "$J$6", f"$K{i}")}>0,"rot",""),"")',
        )
        for col in range(2, 8):
            c = ws.cell(row=i, column=col)
            c.font, c.border = BODY, Border(bottom=thin)
            c.number_format = fmt if col in (3, 4, 5) else ("0%" if col == 6 else "General")
            if col > 2:
                c.alignment = Alignment(horizontal="right")
    first_kpi, last_kpi = r + 1, r + len(KPIS)
    ws.conditional_formatting.add(
        f"G{first_kpi}:G{last_kpi}", CellIsRule(operator="equal", formula=['"rot"'], font=Font(color=RED, bold=True))
    )

    # Block 3: early warning (champion model, latest as-of date).
    r = last_kpi + 3
    ws.cell(row=r - 1, column=2, value="Frühwarnung").font = Font(name="Segoe UI Semibold", size=11)
    header_row(ws, r, ["Kennzahl", "Wert", "", "", "", ""])
    rows = [
        ("Insolvenzwahrscheinlichkeit 12 Monate", f'=IFERROR({cube_value("Risiko 12M", "$J$3")},"–")', "0.0%"),
        (
            "Veränderung zum Vorquartal",
            f'=IFERROR({cube_value("Risiko Veränderung zum Vorquartal", "$J$3")},"–")',
            "+0.0%;-0.0%",
        ),
        ("Altman Z'' (letzte Periode)", f'=IFERROR({cube_value(ZPP_MEASURE, "$J$3")},"–")', "0.00"),
        ("Cash-Potenzial in Mio. EUR", f'=IFERROR({cube_value("Cash-Potenzial", "$J$3", "$J$4")}/10^6,"–")', "#,##0.0"),
    ]
    for i, (label, formula, fmt) in enumerate(rows, start=r + 1):
        ws.cell(row=i, column=2, value=label).font = BODY
        c = ws.cell(row=i, column=3, value=formula)
        c.font, c.number_format, c.alignment = BODY, fmt, Alignment(horizontal="right")
        for col in range(2, 8):
            ws.cell(row=i, column=col).border = Border(bottom=thin)
    risk_row = r + 1
    ws.conditional_formatting.add(
        f"C{risk_row}",
        CellIsRule(
            operator="greaterThanOrEqual",
            formula=["0.10"],
            fill=PatternFill("solid", fgColor="FDECEA"),
            font=Font(color=RED, bold=True),
        ),
    )
    ws.conditional_formatting.add(
        f"C{risk_row}", CellIsRule(operator="between", formula=["0.03", "0.0999999"], font=Font(color=AMBER, bold=True))
    )
    ws.conditional_formatting.add(
        f"C{risk_row}", CellIsRule(operator="lessThan", formula=["0.03"], font=Font(color=GREEN, bold=True))
    )

    footer_row = risk_row + len(rows) + 1
    ws.cell(row=footer_row, column=2, value="Datenstand").font = NOTE
    stand = ws.cell(row=footer_row, column=3, value='=IFERROR(CUBEVALUE(BW_Verbindung,"[Measures].[Datenstand]"),"–")')
    stand.font, stand.number_format, stand.alignment = NOTE, "dd.mm.yyyy", Alignment(horizontal="left")
    ws.cell(
        row=footer_row + 1,
        column=2,
        value="Quelle: SEC EDGAR, ESEF (filings.xbrl.org), GLEIF, EZB · Modell: Bilanzwerk (Power BI)",
    ).font = NOTE
    ws.cell(
        row=footer_row + 2,
        column=2,
        value="Risikobänder: rot ab 10 %, gelb ab 3 % (ADR-007). Δ % gegen Vorjahr; Plan nur für Umsatz.",
    ).font = NOTE

    ws.column_dimensions["J"].hidden = True
    ws.column_dimensions["K"].hidden = True
    ws.print_area = f"A1:G{footer_row + 2}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.oddFooter.left.text = "Bilanzwerk · Management Cockpit"
    ws.oddFooter.right.text = "&D"
    ws.freeze_panes = None


def build_data_sheets(wb: Workbook) -> None:
    for title, columns, note in [
        (
            "Stammdaten",
            MASTER_COLUMNS,
            "Golden Record (aktuelle Version), geladen per Power Query aus marts.dim_company.",
        ),
        ("Risikoliste", RISK_COLUMNS, "Risikoliste Champion-Modell, letzter Stichtag, geladen per Power Query."),
    ]:
        ws = wb.create_sheet(title)
        for i, col in enumerate(columns, start=1):
            c = ws.cell(row=1, column=i, value=col)
            c.font, c.fill = HEADER, HEADER_FILL
            ws.column_dimensions[c.column_letter].width = 22
        ws.cell(row=1, column=len(columns) + 2, value=note).font = NOTE

    ws = wb.create_sheet("Peer")
    ws["A1"] = "Peer-Vergleich"
    ws["A1"].font = Font(name="Segoe UI Semibold", size=14, color=DARK)
    ws["A2"] = (
        "PivotTable auf dem Semantikmodell mit Datenschnitten für Sektor und Geschäftsjahr; "
        "wird von finalize_workbook.ps1 ab Zelle A4 angelegt."
    )
    ws["A2"].font = NOTE


def build_notes(wb: Workbook) -> None:
    ws = wb.create_sheet("Hinweise")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 100
    rows = [
        ("Verbindung", CONNECTION),
        ("Zweck", "Monatsbericht für Controlling: ein Blatt Cockpit mit festem Layout (CUBE-Formeln)."),
        (
            "Aktualisieren",
            "Makro RefreshAndExport (Modul modRefreshAndExport): aktualisiert alle Verbindungen und "
            "speichert das Cockpit als PDF mit Datum im Ordner Export.",
        ),
        (
            "Unternehmen wählen",
            "Cockpit!C3 (Liste aus Stammdaten). Die ID in C5 kommt per XVERWEIS aus dem Golden Record.",
        ),
        (
            "Kennzahlen",
            "Definitionen, Einheiten und Schwellen: dim_kpi im Modell, Quelle dbt/seeds/kpi_definitions.csv.",
        ),
        ("Versionen", "Werte nach Restatements (latest). Das Frühwarnmodell nutzt die Erstveröffentlichung."),
    ]
    for i, (k, v) in enumerate(rows, start=1):
        ws.cell(row=i, column=1, value=k).font = Font(name="Segoe UI Semibold", size=10)
        ws.cell(row=i, column=2, value=v).font = BODY
    wb.defined_names["BW_Verbindung"] = DefinedName("BW_Verbindung", attr_text="Hinweise!$B$1")


def main() -> None:
    wb = Workbook()
    build_cockpit(wb)
    build_data_sheets(wb)
    build_notes(wb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
