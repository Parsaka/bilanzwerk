"""Build the Tableau Public workbook (H4: working-capital potential by sector) from the extract.

  uv run python tableau/build_workbook.py                  # tableau/Bilanzwerk_Working_Capital.twbx

Reads tableau/data/wc_opportunity.csv (scripts/export_tableau.py) and writes a packaged workbook
with the data inside, ready to open in Tableau Public and publish. Sheets, calculated fields,
filters and the dashboard follow tableau/README.md.

The dashboard title states the finding. It is computed here from the same CSV that goes into
the package, with the rule of H4 (latest fiscal year per company), so the title and the bars
always come from one export and no number is typed by hand.
"""

from __future__ import annotations

import argparse
import csv
import json
import uuid
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tableau" / "data"
DS = "federated.bilanzwerk_wc"
ACCENT, GREY = "#1F5AA6", "#B3B3B3"
SIZE = (1200, 800)

COLUMNS = {
    # extract column -> (Tableau datatype, role, type)
    "company_name": ("string", "dimension", "nominal"),
    "cik": ("integer", "dimension", "ordinal"),
    "lei": ("string", "dimension", "nominal"),
    "sector_de": ("string", "dimension", "nominal"),
    "sector_en": ("string", "dimension", "nominal"),
    "fiscal_year": ("integer", "dimension", "ordinal"),
    "dso": ("real", "measure", "quantitative"),
    "dio": ("real", "measure", "quantitative"),
    "dpo": ("real", "measure", "quantitative"),
    "ccc": ("real", "measure", "quantitative"),
    "sector_median_dso": ("real", "measure", "quantitative"),
    "sector_median_dio": ("real", "measure", "quantitative"),
    "sector_median_dpo": ("real", "measure", "quantitative"),
    "revenue_eur": ("real", "measure", "quantitative"),
    "cash_opportunity_eur": ("real", "measure", "quantitative"),
    "cash_opportunity_stretch_eur": ("real", "measure", "quantitative"),
}

# name -> (caption, datatype, role, type, formula); formulas as in tableau/README.md
CALCS = {
    "Calc_Cash_EUR": (
        "Cash-Potenzial EUR",
        "real",
        "measure",
        "quantitative",
        'IF [Parameters].[Param_Szenario] = "Median" THEN [cash_opportunity_eur] '
        "ELSE [cash_opportunity_stretch_eur] END",
    ),
    "Calc_Cash_Bn": ("Cash-Potenzial Mrd. EUR", "real", "measure", "quantitative", "SUM([Calc_Cash_EUR]) / 1e9"),
    "Calc_Delta_DSO": ("Δ DSO", "real", "measure", "quantitative", "[dso] - [sector_median_dso]"),
    "Calc_Delta_DIO": ("Δ DIO", "real", "measure", "quantitative", "[dio] - [sector_median_dio]"),
    "Calc_Delta_DPO": ("Δ DPO", "real", "measure", "quantitative", "[sector_median_dpo] - [dpo]"),
    "Calc_Latest_FY": (
        "Letztes Geschäftsjahr des Unternehmens",
        "boolean",
        "dimension",
        "nominal",
        "[fiscal_year] = { FIXED [cik], [company_name] : MAX([fiscal_year]) }",
    ),
    "Calc_Is_Top": (
        "Größter Hebel",
        "boolean",
        "dimension",
        "nominal",
        "RANK(SUM([Calc_Cash_EUR])) = 1",
    ),
}


def read_extract(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    missing = set(COLUMNS) - set(rows[0] if rows else {})
    if missing:
        raise SystemExit(f"{path} lacks columns {sorted(missing)}: export it with scripts/export_tableau.py")
    return rows


def finding(rows: list[dict]) -> dict:
    """Latest fiscal year per company (as H4), summed by sector: total and the largest sector."""
    latest: dict[tuple, dict] = {}
    for r in rows:
        key = (r["cik"], r["company_name"])
        if key not in latest or int(r["fiscal_year"]) > int(latest[key]["fiscal_year"]):
            latest[key] = r
    by_sector: dict[str, float] = defaultdict(float)
    for r in latest.values():
        by_sector[r["sector_de"]] += float(r["cash_opportunity_eur"] or 0)
    top = max(by_sector, key=by_sector.get)
    years = [int(r["fiscal_year"]) for r in rows]
    return {
        "top_sector": top,
        "top_eur_bn": by_sector[top] / 1e9,
        "total_eur_bn": sum(by_sector.values()) / 1e9,
        "companies": len(latest),
        "sectors": len(by_sector),
        "years": (min(years), max(years)),
    }


def de(x: float) -> str:
    return f"{x:,.1f}".replace(",", " ").replace(".", ",")


def ref(name: str, derivation: str = "None", kind: str = "nk") -> str:
    prefix = {"None": "none", "User": "usr", "Sum": "sum", "Median": "med", "CountD": "ctd"}[derivation]
    return f"[{DS}].[{prefix}:{name}:{kind}]"


def instance(name: str, derivation: str, kind: str, type_: str) -> str:
    prefix = {"None": "none", "User": "usr", "Sum": "sum", "Median": "med", "CountD": "ctd"}[derivation]
    pivot = "key"
    return (
        f"<column-instance column='[{name}]' derivation='{derivation}' "
        f"name='[{prefix}:{name}:{kind}]' pivot='{pivot}' type='{type_}' />"
    )


def column_xml(name: str) -> str:
    if name in CALCS:
        caption, dt, role, type_, formula = CALCS[name]
        return (
            f"<column caption={quoteattr(caption)} datatype='{dt}' name='[{name}]' role='{role}' type='{type_}'>"
            f"<calculation class='tableau' formula={quoteattr(formula)} /></column>"
        )
    dt, role, type_ = COLUMNS[name]
    return f"<column datatype='{dt}' name='[{name}]' role='{role}' type='{type_}' />"


def text_run(text: str, size: int = 12, bold: bool = False, color: str = "#262626") -> str:
    attrs = f"fontcolor='{color}' fontsize='{size}'" + (" bold='true'" if bold else "")
    return f"<run {attrs}>{escape(text)}</run>"


def latest_fy_filter() -> str:
    level = "[none:Calc_Latest_FY:nk]"
    return (
        f"<filter class='categorical' column='{ref('Calc_Latest_FY')}'>"
        f"<groupfilter function='member' level='{level}' member='true' "
        "user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' /></filter>"
    )


def worksheet(name: str, title: str, deps: list[str], instances: list[str], body: str, extra_view: str = "") -> str:
    dep_cols = "".join(column_xml(c) for c in deps)
    return f"""
    <worksheet name={quoteattr(name)}>
      <layout-options><title><formatted-text>{text_run(title, 12, True)}</formatted-text></title></layout-options>
      <table>
        <view>
          <datasources>
            <datasource caption='wc_opportunity' name='{DS}' />
            <datasource name='Parameters' />
          </datasources>
          <datasource-dependencies datasource='{DS}'>{dep_cols}{"".join(instances)}</datasource-dependencies>
          <datasource-dependencies datasource='Parameters'>{parameter_column()}</datasource-dependencies>
          {latest_fy_filter()}
          {extra_view}
          <slices><column>{ref("Calc_Latest_FY")}</column></slices>
          <aggregation value='true' />
        </view>
        <style />
        {body}
      </table>
      <simple-id uuid='{{{uuid.uuid5(uuid.NAMESPACE_URL, "bilanzwerk/tableau/" + name)}}}' />
    </worksheet>"""


def parameter_column() -> str:
    return (
        "<column caption='Szenario' datatype='string' name='[Param_Szenario]' param-domain-type='list' "
        "role='measure' type='nominal' value='&quot;Median&quot;'>"
        "<calculation class='tableau' formula='&quot;Median&quot;' />"
        "<members><member value='&quot;Median&quot;' /><member value='&quot;Oberes Quartil&quot;' /></members>"
        "</column>"
    )


def bar_pane(color_field: str | None = None, label: str | None = None) -> str:
    enc = ""
    if color_field or label:
        enc = "<encodings>"
        if color_field:
            enc += f"<color column='{color_field}' />"
        if label:
            enc += f"<text column='{label}' />"
        enc += "</encodings>"
    show_labels = (
        "<style><style-rule element='mark'><format attr='mark-labels-show' value='true' /></style-rule></style>"
        if label
        else ""
    )
    return (
        "<panes><pane selection-relaxation-option='selection-relaxation-allow'>"
        f"<view><breakdown value='auto' /></view><mark class='Bar' />{enc}{show_labels}</pane></panes>"
    )


def build_twb(f: dict, csv_dir: str) -> str:
    cash_bn = "Calc_Cash_Bn"
    title = (
        f"{f['top_sector']} hat den größten Hebel: {de(f['top_eur_bn'])} Mrd. EUR Working Capital "
        f"über dem Sektormedian (gesamt {de(f['total_eur_bn'])} Mrd. EUR)"
    )
    sector_dims = ["sector_de"]
    calc_deps = [
        "Calc_Cash_EUR",
        "Calc_Cash_Bn",
        "Calc_Latest_FY",
        "cash_opportunity_eur",
        "cash_opportunity_stretch_eur",
        "fiscal_year",
        "cik",
        "company_name",
    ]

    bridge = worksheet(
        "Brücke nach Sektor",
        "Working-Capital-Potenzial nach Sektor (Mrd. EUR, letztes Geschäftsjahr je Unternehmen)",
        sector_dims + calc_deps + ["Calc_Is_Top"],
        [
            instance("sector_de", "None", "nk", "nominal"),
            instance(cash_bn, "User", "qk", "quantitative"),
            instance("Calc_Is_Top", "User", "nk", "nominal"),
            instance("Calc_Latest_FY", "None", "nk", "nominal"),
        ],
        bar_pane(ref("Calc_Is_Top", "User"), ref(cash_bn, "User", "qk"))
        + f"<rows>{ref('sector_de')}</rows><cols>{ref(cash_bn, 'User', 'qk')}</cols>",
        extra_view=(
            f"<sort class='computed' column='{ref('sector_de')}' direction='DESC' "
            f"using='{ref(cash_bn, 'User', 'qk')}' />"
        ),
    )
    top20 = worksheet(
        "Top 20 Unternehmen",
        "Die 20 Unternehmen mit dem größten Potenzial (Mrd. EUR)",
        ["company_name", "sector_de", *calc_deps],
        [
            instance("company_name", "None", "nk", "nominal"),
            instance(cash_bn, "User", "qk", "quantitative"),
            instance("Calc_Latest_FY", "None", "nk", "nominal"),
        ],
        bar_pane(None, ref(cash_bn, "User", "qk"))
        + f"<rows>{ref('company_name')}</rows><cols>{ref(cash_bn, 'User', 'qk')}</cols>",
        extra_view=(
            f"<filter class='categorical' column='{ref('company_name')}'>"
            "<groupfilter count='20' end='top' function='end' units='records' user:ui-marker='end' "
            "user:ui-top-by-field='true'>"
            "<groupfilter direction='DESC' expression='SUM([Calc_Cash_EUR])' function='order' user:ui-marker='order'>"
            "<groupfilter function='level-members' level='[none:company_name:nk]' "
            "user:ui-enumeration='all' user:ui-marker='enumerate' /></groupfilter></groupfilter></filter>"
            f"<sort class='computed' column='{ref('company_name')}' direction='DESC' "
            f"using='{ref(cash_bn, 'User', 'qk')}' />"
        ),
    )
    lever_cols = ["Calc_Delta_DSO", "Calc_Delta_DIO", "Calc_Delta_DPO"]
    levers = worksheet(
        "Wo das Cash liegt",
        "Abstand zum Sektormedian in Tagen (Median der Unternehmen): Forderungen, Vorräte, Lieferanten",
        [
            "sector_de",
            *lever_cols,
            "dso",
            "dio",
            "dpo",
            "sector_median_dso",
            "sector_median_dio",
            "sector_median_dpo",
            *calc_deps,
        ],
        [instance("sector_de", "None", "nk", "nominal")]
        + [instance(c, "Median", "qk", "quantitative") for c in lever_cols]
        + [instance("Calc_Latest_FY", "None", "nk", "nominal")],
        bar_pane()
        + f"<rows>{ref('sector_de')}</rows>"
        + "<cols>("
        + " + ".join(ref(c, "Median", "qk") for c in lever_cols)
        + ")</cols>",
    )
    kpi = worksheet(
        "KPI-Zeile",
        "Gesamt",
        ["company_name", "sector_de", *calc_deps],
        [
            instance(cash_bn, "User", "qk", "quantitative"),
            instance("company_name", "CountD", "qk", "quantitative"),
            instance("sector_de", "CountD", "qk", "quantitative"),
            instance("Calc_Latest_FY", "None", "nk", "nominal"),
        ],
        "<panes><pane selection-relaxation-option='selection-relaxation-allow'>"
        "<view><breakdown value='auto' /></view><mark class='Text' /><encodings>"
        f"<text column='{ref(cash_bn, 'User', 'qk')}' />"
        f"<text column='{ref('company_name', 'CountD', 'qk')}' />"
        f"<text column='{ref('sector_de', 'CountD', 'qk')}' />"
        "</encodings></pane></panes><rows /><cols />",
    )

    cols = "".join(
        f"<column datatype='{dt}' name='{name}' ordinal='{i}' />"
        for i, (name, (dt, _, _)) in enumerate(COLUMNS.items())
    )
    ds_columns = "".join(column_xml(c) for c in [*COLUMNS, *CALCS])
    footer = (
        f"Datenstand: Export der Geschäftsjahre {f['years'][0]} bis {f['years'][1]} · Quellen: SEC EDGAR, ESEF über "
        "filings.xbrl.org, GLEIF, EZB · github.com/Parsaka/bilanzwerk"
    )
    W, H = SIZE

    def z(id_, name, x, y, w, h):
        # zone coordinates in 1/100000 of the dashboard
        return (
            f"<zone h='{h * 100000 // H}' id='{id_}' name={quoteattr(name)} "
            f"w='{w * 100000 // W}' x='{x * 100000 // W}' y='{y * 100000 // H}' />"
        )

    def ztext(id_, text, x, y, w, h, size, bold=False, color="#262626"):
        return (
            f"<zone h='{h * 100000 // H}' id='{id_}' type-v2='text' w='{w * 100000 // W}' "
            f"x='{x * 100000 // W}' y='{y * 100000 // H}'>"
            f"<formatted-text>{text_run(text, size, bold, color)}</formatted-text></zone>"
        )

    dashboard = f"""
    <dashboard name='Working-Capital-Potenzial'>
      <style />
      <size maxheight='{H}' maxwidth='{W}' minheight='{H}' minwidth='{W}' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
          {ztext(2, title, 16, 8, 1168, 56, 18, True)}
          {z(3, "KPI-Zeile", 16, 72, 1168, 60)}
          {z(4, "Brücke nach Sektor", 16, 140, 584, 600)}
          {z(5, "Top 20 Unternehmen", 608, 140, 576, 330)}
          {z(6, "Wo das Cash liegt", 608, 478, 576, 262)}
          {ztext(7, footer, 16, 748, 1168, 40, 9, False, "#8C8C8C")}
        </zone>
      </zones>
      <simple-id uuid='{{{uuid.uuid5(uuid.NAMESPACE_URL, "bilanzwerk/tableau/dashboard")}}}' />
    </dashboard>"""

    return f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook original-version='18.1' source-build='2023.3.0 (20233.23.1017.0948)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <_.fcp.MarkAnimation.true...MarkAnimation />
    <SheetIdentifierTracking />
    <WindowsPersistSimpleIdentifiers />
  </document-format-change-manifest>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
    <datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>
      <aliases enabled='yes' />
      {parameter_column()}
    </datasource>
    <datasource caption='wc_opportunity' inline='true' name='{DS}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='wc_opportunity' name='textscan.bilanzwerk_wc'>
            <connection class='textscan' directory={quoteattr(csv_dir)}
                        filename='wc_opportunity.csv' password='' server='' />
          </named-connection>
        </named-connections>
        <relation connection='textscan.bilanzwerk_wc' name='wc_opportunity.csv'
                  table='[wc_opportunity#csv]' type='table'>
          <columns character-set='UTF-8' header='yes' locale='en_US' separator=','>{cols}</columns>
        </relation>
      </connection>
      <aliases enabled='yes' />
      {ds_columns}
      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />
    </datasource>
  </datasources>
  <worksheets>{bridge}{top20}{levers}{kpi}
  </worksheets>
  <dashboards>{dashboard}
  </dashboards>
</workbook>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--csv", type=Path, default=DATA / "wc_opportunity.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "tableau" / "Bilanzwerk_Working_Capital.twbx")
    args = parser.parse_args()
    rows = read_extract(args.csv)
    f = finding(rows)
    twb = build_twb(f, "Data/wc_opportunity")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Bilanzwerk_Working_Capital.twb", twb)
        zf.write(args.csv, "Data/wc_opportunity/wc_opportunity.csv")
    (args.out.with_suffix(".finding.json")).write_text(json.dumps(f, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out}: {f['companies']} companies, title sector {f['top_sector']}")


if __name__ == "__main__":
    main()
