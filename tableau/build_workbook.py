"""Build the Tableau Public workbook (H4: working-capital potential by sector) from the extract.

  uv run python tableau/build_workbook.py                  # tableau/Bilanzwerk_Working_Capital.twbx

Reads tableau/data/wc_opportunity.csv (scripts/export_tableau.py) and writes a packaged workbook
with the data inside, ready to open in Tableau Public and publish. Sheets, calculated fields,
filters and the dashboard follow tableau/README.md.

Tableau Public only opens and saves workbooks whose data is an extract, so the CSV is loaded into
a Hyper file (Data/Extracts/wc_opportunity.hyper) with tableauhyperapi (extra `tableau`):

  uv run --extra tableau python tableau/build_workbook.py

The dashboard title states the finding. It is computed here from the same CSV that goes into
the package, with the rule of H4 (latest fiscal year per company), so the title and the bars
always come from one export and no number is typed by hand.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
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
SHEETS = ["Brücke nach Sektor", "Top 20 Unternehmen", "Wo das Cash liegt", "KPI-Zeile"]
DASHBOARD = "Working-Capital-Potenzial"
CSV_DIR, HYPER_PATH = "Data/wc_opportunity", "Data/Extracts/wc_opportunity.hyper"

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

CAPTIONS = {"company_name": "Unternehmen", "sector_de": "Sektor", "fiscal_year": "Geschäftsjahr"}
FORMATS = {"Calc_Cash_Bn": "n#,##0.0;-#,##0.0"}

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
}


def read_extract(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    missing = set(COLUMNS) - set(rows[0] if rows else {})
    if missing:
        raise SystemExit(f"{path} lacks columns {sorted(missing)}: export it with scripts/export_tableau.py")
    return rows


def write_hyper(csv_path: Path, hyper_path: Path) -> int:
    """Copy the CSV into a Hyper extract (table Extract.Extract) with the types of COLUMNS."""
    from tableauhyperapi import (
        Connection,
        CreateMode,
        HyperProcess,
        Nullability,
        SqlType,
        TableDefinition,
        TableName,
        Telemetry,
        escape_string_literal,
    )

    types = {"string": SqlType.text(), "integer": SqlType.big_int(), "real": SqlType.double()}
    table = TableDefinition(
        TableName("Extract", "Extract"),
        [TableDefinition.Column(name, types[dt], Nullability.NULLABLE) for name, (dt, _, _) in COLUMNS.items()],
    )
    with (
        HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_config": ""}) as hyper,
        Connection(hyper.endpoint, str(hyper_path), CreateMode.CREATE_AND_REPLACE) as conn,
    ):
        conn.catalog.create_schema("Extract")
        conn.catalog.create_table(table)
        return conn.execute_command(
            f"COPY {table.table_name} FROM {escape_string_literal(str(csv_path))} "
            "WITH (format csv, header true, delimiter ',', null '')"
        )


def finding(rows: list[dict]) -> dict:
    """Latest fiscal year per company (as H4), summed by sector: total and the largest sector.

    All rows of that year count, as in the workbook's filter [Calc_Latest_FY], so the title and the
    bars agree even where the extract holds two rows for one company and fiscal year.
    """
    latest: dict[tuple, int] = {}
    for r in rows:
        key = (r["cik"], r["company_name"])
        latest[key] = max(latest.get(key, int(r["fiscal_year"])), int(r["fiscal_year"]))
    by_sector: dict[str, float] = defaultdict(float)
    for r in rows:
        if int(r["fiscal_year"]) == latest[(r["cik"], r["company_name"])]:
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
    return f"{x:,.1f}".replace(",", " ").replace(".", ",").replace(" ", ".")


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
    fmt = f" default-format={quoteattr(FORMATS[name])}" if name in FORMATS else ""
    if name in CALCS:
        caption, dt, role, type_, formula = CALCS[name]
        return (
            f"<column caption={quoteattr(caption)} datatype='{dt}'{fmt} name='[{name}]' role='{role}' type='{type_}'>"
            f"<calculation class='tableau' formula={quoteattr(formula)} /></column>"
        )
    dt, role, type_ = COLUMNS[name]
    caption = f" caption={quoteattr(CAPTIONS[name])}" if name in CAPTIONS else ""
    return f"<column{caption} datatype='{dt}'{fmt} name='[{name}]' role='{role}' type='{type_}' />"


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


def worksheet(
    name: str, title: str, deps: list[str], instances: list[str], body: str, extra_view: str = "", style: str = ""
) -> str:
    dep_cols = "".join(column_xml(c) for c in deps)
    # the sheet titles name the dimension already; field labels ("Sektor") only cost a row
    hide_field_labels = (
        "<style-rule element='worksheet'><format attr='display-field-labels' scope='rows' value='false' /></style-rule>"
    )
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
        <style>{hide_field_labels}{style}</style>
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


def bar_pane(color: str, label: str | None = None) -> str:
    enc = f"<encodings><text column='{label}' /></encodings>" if label else ""
    labels = "<format attr='mark-labels-show' value='true' />" if label else ""
    return (
        "<panes><pane selection-relaxation-option='selection-relaxation-allow'>"
        f"<view><breakdown value='auto' /></view><mark class='Bar' />{enc}"
        f"<style><style-rule element='mark'><format attr='mark-color' value='{color}' />{labels}</style-rule></style>"
        "</pane></panes>"
    )


def windows() -> str:
    """Tableau needs an active sheet to open a workbook: the dashboard, with the sheets behind it."""
    cards = (
        "<cards><edge name='left'><strip size='160'><card type='pages' /><card type='filters' />"
        "<card type='marks' /></strip></edge><edge name='top'><strip size='2147483647'><card type='columns' />"
        "</strip><strip size='2147483647'><card type='rows' /></strip><strip size='31'><card type='title' />"
        "</strip></edge></cards>"
    )

    def sid(name: str) -> str:
        return f"<simple-id uuid='{{{uuid.uuid5(uuid.NAMESPACE_URL, 'bilanzwerk/tableau/window/' + name)}}}' />"

    sheets = "".join(
        f"\n    <window class='worksheet' hidden='true' maximized='true' name={quoteattr(n)}>{cards}{sid(n)}</window>"
        for n in SHEETS
    )
    viewpoints = "".join(f"<viewpoint name={quoteattr(n)}><zoom type='entire-view' /></viewpoint>" for n in SHEETS)
    return (
        f"<windows source-height='30'>{sheets}\n    <window class='dashboard' maximized='true' name='{DASHBOARD}'>"
        f"<viewpoints>{viewpoints}</viewpoints><active id='-1' /><device-preview visible='false' />"
        f"{sid(DASHBOARD)}</window>\n  </windows>"
    )


def build_twb(f: dict, csv_dir: str = CSV_DIR, hyper_path: str = HYPER_PATH) -> str:
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
        "Potenzial nach Sektor (Mrd. EUR)",
        sector_dims + calc_deps,
        [
            instance("sector_de", "None", "nk", "nominal"),
            instance(cash_bn, "User", "qk", "quantitative"),
            instance("Calc_Latest_FY", "None", "nk", "nominal"),
        ],
        bar_pane(ACCENT, ref(cash_bn, "User", "qk"))
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
        bar_pane(GREY, ref(cash_bn, "User", "qk"))
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
        "Tage über dem Sektormedian: DSO, DIO, DPO",
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
        + [instance(cash_bn, "User", "qk", "quantitative"), instance("Calc_Latest_FY", "None", "nk", "nominal")],
        bar_pane(GREY)
        + f"<rows>{ref('sector_de')}</rows>"
        + "<cols>("
        + " + ".join(ref(c, "Median", "qk") for c in lever_cols)
        + ")</cols>",
        extra_view=(
            f"<sort class='computed' column='{ref('sector_de')}' direction='DESC' "
            f"using='{ref(cash_bn, 'User', 'qk')}' />"
        ),
    )
    kpi = worksheet(
        "KPI-Zeile",
        "Gesamt",
        ["company_name", "sector_de", *calc_deps],
        [
            instance(cash_bn, "User", "qk", "quantitative"),
            instance("cik", "CountD", "qk", "quantitative"),
            instance("sector_de", "CountD", "qk", "quantitative"),
            instance("Calc_Latest_FY", "None", "nk", "nominal"),
        ],
        "<panes><pane selection-relaxation-option='selection-relaxation-allow'>"
        "<view><breakdown value='auto' /></view><mark class='Text' /><encodings>"
        f"<text column='{ref(cash_bn, 'User', 'qk')}' />"
        f"<text column='{ref('cik', 'CountD', 'qk')}' />"
        f"<text column='{ref('sector_de', 'CountD', 'qk')}' />"
        "</encodings><customized-label><formatted-text>"
        + text_run("Gesamt ", 12, True)
        + text_run(f"<{ref(cash_bn, 'User', 'qk')}>", 12, True, ACCENT)
        + text_run(" Mrd. EUR · ", 12, True)
        + text_run(f"<{ref('cik', 'CountD', 'qk')}>", 12)
        + text_run(" Unternehmen · ", 12)
        + text_run(f"<{ref('sector_de', 'CountD', 'qk')}>", 12)
        + text_run(" Sektoren", 12)
        + "</formatted-text></customized-label>"
        "<style><style-rule element='mark'><format attr='mark-labels-show' value='true' /></style-rule></style>"
        "</pane></panes><rows /><cols />",
    )

    cols = "".join(
        f"<column datatype='{dt}' name='{name}' ordinal='{i}' />"
        for i, (name, (dt, _, _)) in enumerate(COLUMNS.items())
    )
    ds_columns = "".join(column_xml(c) for c in [*COLUMNS, *CALCS])
    footer = (
        f"Geschäftsjahre {f['years'][0]} bis {f['years'][1]} · Quellen: SEC EDGAR, ESEF (filings.xbrl.org), "
        "GLEIF, EZB · github.com/Parsaka/bilanzwerk"
    )
    W, H = SIZE

    def z(id_, name, x, y, w, h, show_title=True):
        # zone coordinates in 1/100000 of the dashboard
        return (
            f"<zone h='{h * 100000 // H}' id='{id_}' name={quoteattr(name)} "
            + ("" if show_title else "show-title='false' ")
            + f"w='{w * 100000 // W}' x='{x * 100000 // W}' y='{y * 100000 // H}' />"
        )

    def ztext(id_, text, x, y, w, h, size, bold=False, color="#262626"):
        return (
            f"<zone h='{h * 100000 // H}' id='{id_}' type-v2='text' w='{w * 100000 // W}' "
            f"x='{x * 100000 // W}' y='{y * 100000 // H}'>"
            f"<formatted-text>{text_run(text, size, bold, color)}</formatted-text></zone>"
        )

    dashboard = f"""
    <dashboard name='{DASHBOARD}'>
      <style />
      <size maxheight='{H}' maxwidth='{W}' minheight='{H}' minwidth='{W}' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
          {ztext(2, title, 16, 8, 1168, 76, 14, True)}
          {z(3, "KPI-Zeile", 16, 88, 1168, 48, show_title=False)}
          {z(4, "Brücke nach Sektor", 16, 140, 584, 300)}
          {z(6, "Wo das Cash liegt", 16, 448, 584, 292)}
          {z(5, "Top 20 Unternehmen", 608, 140, 576, 600)}
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
      <extract count='-1' enabled='true' units='records'>
        <connection access_mode='readonly' author-locale='en_US' class='hyper' dbname={quoteattr(hyper_path)}
                    default-settings='hyper' schema='Extract' sslmode='' tablename='Extract' username='tableau'>
          <relation name='Extract' table='[Extract].[Extract]' type='table' />
        </connection>
      </extract>
      <layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic'
              measure-percentage='0.4' show-structure='true' />
    </datasource>
  </datasources>
  <worksheets>{bridge}{top20}{levers}{kpi}
  </worksheets>
  <dashboards>{dashboard}
  </dashboards>
  {windows()}
</workbook>
"""


def check_against_h4(f: dict, h4: dict, tolerance_bn: float = 0.5) -> None:
    """The workbook title and H4 come from the same mart; if they disagree, one of them is wrong."""
    problems = []
    if f["top_sector"] != h4["top_sector"]:
        problems.append(f"top sector {f['top_sector']!r} vs H4 {h4['top_sector']!r}")
    if abs(f["total_eur_bn"] - h4["total_eur_bn"]) > tolerance_bn:
        problems.append(f"total {f['total_eur_bn']:.1f} bn vs H4 {h4['total_eur_bn']:.1f} bn")
    if problems:
        raise SystemExit("Tableau finding disagrees with H4: " + "; ".join(problems))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--csv", type=Path, default=DATA / "wc_opportunity.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "tableau" / "Bilanzwerk_Working_Capital.twbx")
    parser.add_argument("--check-answer", type=Path, help="answer.json of the same run: the title must agree with H4")
    args = parser.parse_args()
    rows = read_extract(args.csv)
    f = finding(rows)
    if args.check_answer:
        check_against_h4(f, json.loads(args.check_answer.read_text())["H4"])
    twb = build_twb(f)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        hyper = Path(tmp) / "wc_opportunity.hyper"
        loaded = write_hyper(args.csv, hyper)
        if loaded != len(rows):
            raise SystemExit(f"Hyper extract holds {loaded} rows, the CSV {len(rows)}")
        with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Bilanzwerk_Working_Capital.twb", twb)
            zf.write(args.csv, f"{CSV_DIR}/wc_opportunity.csv")
            zf.write(hyper, HYPER_PATH)
    (args.out.with_suffix(".finding.json")).write_text(json.dumps(f, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out}: {f['companies']} companies, title sector {f['top_sector']}")


if __name__ == "__main__":
    main()
