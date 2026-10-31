"""Render the Power BI semantic model (TMDL, PBIP format) from model.yml and the data contracts.

  python powerbi/tools/generate_tmdl.py

Columns are taken from docs/data-contracts/*.yml, so the model can never drift from the marts:
a renamed mart column breaks the contract check first, and the regenerated model follows.
The Warehouse endpoint is a placeholder (#{SQL_ENDPOINT}#, #{WAREHOUSE}#) that the deployment
step replaces (scripts/deploy_semantic_model.py / Fabric deployment pipeline parameters).
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / "powerbi"
MODEL_DIR = PBI / "Bilanzwerk.SemanticModel"
DEF = MODEL_DIR / "definition"
CONTRACTS = ROOT / "docs" / "data-contracts"
NS = uuid.UUID("6f1c3c5e-1b7a-4f5e-9d0a-3b1e2a9c7d11")

DATATYPE = {
    "string": "string",
    "integer": "int64",
    "float": "double",
    "decimal": "decimal",
    "date": "dateTime",
    "timestamp": "dateTime",
}
FORMAT = {"date": "dd.MM.yyyy", "timestamp": "dd.MM.yyyy HH:mm", "float": "#,0.00", "decimal": "#,0.00", "integer": "0"}


def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    if name.isascii() and name.replace("_", "").isalnum() and not name[0].isdigit():
        return name
    return "'" + name.replace("'", "''") + "'"


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "|".join(parts)))


def description(text: str | None, indent: str) -> list[str]:
    return [f"{indent}/// {line}" for line in (text or "").split("\n") if line.strip()]


def expression_lines(expr: str, indent: str) -> list[str]:
    lines = expr.strip("\n").split("\n")
    if len(lines) == 1:
        return [lines[0]]
    return [""] + [f"{indent}{line}" if line.strip() else "" for line in lines]


def render_table(
    name: str, cfg: dict, columns: list[dict], measures: list[dict], schema: str, foreign_keys: set[str]
) -> str:
    out = description(cfg.get("description"), "")
    out.append(f"table {q(name)}")
    if cfg.get("hidden"):
        out.append("\tisHidden")
    if cfg.get("mark_as_date"):
        out.append("\tdataCategory: Time")
    out.append(f"\tlineageTag: {tag('table', name)}")
    out.append(f"\tsourceLineageTag: [{schema}].[{name}]")
    out.append("")
    for m in measures:
        out += description(m.get("description"), "\t")
        expr = expression_lines(m["expression"], "\t\t\t")
        out.append(f"\tmeasure {q(m['name'])} = {expr[0]}".rstrip())
        out += expr[1:]
        if m.get("format"):
            out.append(f"\t\tformatString: {m['format']}")
        if m.get("folder"):
            out.append(f"\t\tdisplayFolder: {m['folder']}")
        if m.get("hidden"):
            out.append("\t\tisHidden")
        out.append(f"\t\tlineageTag: {tag('measure', name, m['name'])}")
        out.append("")
    hidden = set(cfg.get("hidden_columns", [])) | foreign_keys
    for col in columns:
        c, t = col["name"], col["type"]
        out.append(f"\tcolumn {q(c)}")
        out.append(f"\t\tdataType: {DATATYPE[t]}")
        if t in FORMAT and not c.endswith("_key"):
            out.append(f"\t\tformatString: {FORMAT[t]}")
        if c == cfg.get("key") or c in hidden or (c.endswith("_key") and name.startswith("fact_")):
            out.append("\t\tisHidden")
        if c == cfg.get("key") and cfg.get("mark_as_date"):
            out.append("\t\tisKey")
        out.append("\t\tsummarizeBy: none")
        out.append(f"\t\tsourceColumn: {c}")
        out.append(f"\t\tlineageTag: {tag('column', name, c)}")
        out.append(f"\t\tsourceLineageTag: {c}")
        out.append("")
    out.append(f"\tpartition {q(name)} = entity")
    out.append("\t\tmode: directLake")
    out.append("\t\tsource")
    out.append(f"\t\t\tentityName: {name}")
    out.append(f"\t\t\tschemaName: {schema}")
    out.append("\t\t\texpressionSource: DatabaseQuery")
    out.append("")
    if cfg.get("mark_as_date"):
        out.append("\tannotation __PBI_TimeIntelligenceEnabled = 0")
        out.append("")
    return "\n".join(out)


def render_calc_group(cg: dict) -> str:
    out = description(cg.get("description"), "")
    out.append(f"table {q(cg['name'])}")
    out.append(f"\tlineageTag: {tag('table', cg['name'])}")
    out.append("")
    out.append("\tcalculationGroup")
    out.append(f"\t\tprecedence: {cg['precedence']}")
    out.append("")
    for i, item in enumerate(cg["items"]):
        name, expr = item[0], item[1]
        out.append(f"\t\tcalculationItem {q(name)} = {expr}")
        out.append(f"\t\t\tordinal: {i}")
        if len(item) > 2:
            out.append(f'\t\t\tformatStringDefinition = "{item[2]}"')
        out.append("")
    out.append(f"\tcolumn {q(cg['column'])}")
    out.append("\t\tdataType: string")
    out.append("\t\tsummarizeBy: none")
    out.append("\t\tsourceColumn: Name")
    out.append("\t\tsortByColumn: Ordinal")
    out.append(f"\t\tlineageTag: {tag('column', cg['name'], cg['column'])}")
    out.append("")
    out.append("\tcolumn Ordinal")
    out.append("\t\tdataType: int64")
    out.append("\t\tisHidden")
    out.append("\t\tsummarizeBy: none")
    out.append("\t\tsourceColumn: Ordinal")
    out.append(f"\t\tlineageTag: {tag('column', cg['name'], 'Ordinal')}")
    out.append("")
    out.append(f"\tpartition {q(cg['name'])} = calculationGroup")
    out.append("\t\tmode: import")
    out.append("")
    return "\n".join(out)


def render_field_parameter(fp: dict, measure_table: dict[str, str]) -> str:
    name = fp["name"]
    rows = ",\n".join(
        f"\t\t\t\t(\"{m}\", NAMEOF('{measure_table[m]}'[{m.replace(']', ']]')}]), {i})"
        for i, m in enumerate(fp["measures"])
    )
    out = description(fp.get("description"), "")
    out += [
        f"table {q(name)}",
        f"\tlineageTag: {tag('table', name)}",
        "",
        f"\tcolumn {q(name)}",
        "\t\tdataType: string",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value1]",
        f"\t\tsortByColumn: {q(name + ' Reihenfolge')}",
        f"\t\tlineageTag: {tag('column', name, 'value')}",
        "",
        "\t\trelatedColumnDetails",
        f"\t\t\tgroupByColumn: {q(name + ' Felder')}",
        "",
        f"\tcolumn {q(name + ' Felder')}",
        "\t\tdataType: string",
        "\t\tisHidden",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value2]",
        f"\t\tlineageTag: {tag('column', name, 'fields')}",
        "",
        "\t\textendedProperty ParameterMetadata =",
        "\t\t\t\t{",
        '\t\t\t\t  "version": 3,',
        '\t\t\t\t  "kind": 2',
        "\t\t\t\t}",
        "",
        f"\tcolumn {q(name + ' Reihenfolge')}",
        "\t\tdataType: int64",
        "\t\tisHidden",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value3]",
        f"\t\tlineageTag: {tag('column', name, 'order')}",
        "",
        f"\tpartition {q(name)} = calculated",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\t{",
        rows,
        "\t\t\t\t}",
        "",
    ]
    return "\n".join(out)


def render_role(role: dict) -> str:
    out = description(role.get("description"), "")
    out.append(f"role {q(role['name'])}")
    out.append(f"\tmodelPermission: {role['permission']}")
    out.append("")
    for table, expr in (role.get("filters") or {}).items():
        out.append(f"\ttablePermission {q(table)} = {expr}")
        out.append("")
    for table, cols in (role.get("ols") or {}).items():
        out.append(f"\ttablePermission {q(table)}")
        for c in cols:
            out.append(f"\t\tcolumnPermission {q(c)} = none")
        out.append("")
    return "\n".join(out)


def dax_text(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def label_measures(pages: dict) -> list[dict]:
    """Bilingual page titles and the footer, switched by the Sprache table (spec: English toggle)."""
    out = []
    for i, page in enumerate(pages["pages"], start=1):
        de = f"{page['de']['name']}: {page['de']['question']}"
        en = f"{page['en']['name']}: {page['en']['question']}"
        out.append(
            {
                "name": f"Titel {i:02d}",
                "expression": f'IF ( SELECTEDVALUE ( Sprache[Code], "DE" ) = "EN", {dax_text(en)}, {dax_text(de)} )',
                "description": f"Seitentitel {i:02d} ({page['id']}), Deutsch oder Englisch je nach Sprachauswahl.",
                "folder": "Beschriftungen",
            }
        )
    src = pages["source_line"]
    out.append(
        {
            "name": "Fußzeile",
            "expression": "\n".join(
                [
                    "VAR _stand = CALCULATE ( MAX ( fact_financial_line[available_at] ), REMOVEFILTERS () )",
                    'VAR _en = SELECTEDVALUE ( Sprache[Code], "DE" ) = "EN"',
                    "RETURN",
                    '    IF ( _en, "Data cut-off: " & FORMAT ( _stand, "yyyy-MM-dd" ),',
                    '        "Datenstand: " & FORMAT ( _stand, "dd.MM.yyyy" ) )',
                    f'        & " · " & IF ( _en, {dax_text(src["en"])}, {dax_text(src["de"])} )',
                ]
            ),
            "description": "Fußzeile jeder Seite: Datenstand (letzter verfügbarer Wert im Modell) und Quellen.",
            "folder": "Beschriftungen",
        }
    )
    return out


def render_language_table(measures: list[dict]) -> str:
    out = [
        "/// Sprachauswahl der Berichtsseiten (Deutsch Standard, Englisch umschaltbar).",
        "/// Steuert die Messungen im Ordner Beschriftungen.",
        "table Sprache",
        f"\tlineageTag: {tag('table', 'Sprache')}",
        "",
    ]
    for m in measures:
        out += description(m["description"], "\t")
        expr = expression_lines(m["expression"], "\t\t\t")
        out.append(f"\tmeasure {q(m['name'])} = {expr[0]}".rstrip())
        out += expr[1:]
        out.append(f"\t\tdisplayFolder: {m['folder']}")
        out.append(f"\t\tlineageTag: {tag('measure', 'Sprache', m['name'])}")
        out.append("")
    for col, typ, extra in [
        ("Sprache", "string", ["\t\tsortByColumn: Reihenfolge"]),
        ("Code", "string", []),
        ("Reihenfolge", "int64", ["\t\tisHidden"]),
    ]:
        out += [
            f"\tcolumn {col}",
            f"\t\tdataType: {typ}",
            *extra,
            "\t\tsummarizeBy: none",
            f"\t\tsourceColumn: [{col}]",
            f"\t\tlineageTag: {tag('column', 'Sprache', col)}",
            "",
        ]
    out += [
        "\tpartition Sprache = calculated",
        "\t\tmode: import",
        '\t\tsource = DATATABLE ( "Sprache", STRING, "Code", STRING, "Reihenfolge", INTEGER, '
        '{ { "Deutsch", "DE", 0 }, { "English", "EN", 1 } } )',
        "",
    ]
    return "\n".join(out)


def load_columns(name: str, cfg: dict) -> list[dict]:
    if "columns" in cfg:
        return cfg["columns"]
    contract = yaml.safe_load((CONTRACTS / f"{name}.yml").read_text())
    return contract["columns"]


def main() -> None:
    model = yaml.safe_load((PBI / "model.yml").read_text())
    if DEF.exists():
        shutil.rmtree(DEF)
    (DEF / "tables").mkdir(parents=True)
    (DEF / "roles").mkdir()
    (DEF / "cultures").mkdir()

    measures_by_table: dict[str, list[dict]] = {}
    measure_table: dict[str, str] = {}
    for m in model["measures"]:
        measures_by_table.setdefault(m["table"], []).append(m)
        measure_table[m["name"]] = m["table"]
        assert m.get("description") and m.get("folder"), f"measure {m['name']} needs description and folder"

    foreign_keys: dict[str, set[str]] = {}
    for frm, _ in model["relationships"]:
        tbl, col = frm.split(".", 1)
        foreign_keys.setdefault(tbl, set()).add(col)

    table_names = []
    for name, cfg in model["tables"].items():
        schema = cfg.get("schema", model["warehouse_schema"])
        text = render_table(
            name, cfg, load_columns(name, cfg), measures_by_table.get(name, []), schema, foreign_keys.get(name, set())
        )
        (DEF / "tables" / f"{name}.tmdl").write_text(text, encoding="utf-8")
        table_names.append(name)
    for cg in model["calculation_groups"]:
        (DEF / "tables" / f"{cg['name']}.tmdl").write_text(render_calc_group(cg), encoding="utf-8")
        table_names.append(cg["name"])
    for fp in model["field_parameters"]:
        (DEF / "tables" / f"{fp['name']}.tmdl").write_text(render_field_parameter(fp, measure_table), encoding="utf-8")
        table_names.append(fp["name"])
    labels = label_measures(yaml.safe_load((PBI / "report" / "pages.yml").read_text()))
    (DEF / "tables" / "Sprache.tmdl").write_text(render_language_table(labels), encoding="utf-8")
    table_names.append("Sprache")

    rel = []
    for frm, to in model["relationships"]:
        rel += [f"relationship {tag('rel', frm, to)}", f"\tfromColumn: {frm}", f"\ttoColumn: {to}", ""]
    (DEF / "relationships.tmdl").write_text("\n".join(rel), encoding="utf-8")

    for role in model["roles"]:
        (DEF / "roles" / f"{role['name']}.tmdl").write_text(render_role(role), encoding="utf-8")

    (DEF / "expressions.tmdl").write_text(
        "/// Direct Lake source: the Fabric Warehouse. Placeholders are replaced at deployment.\n"
        "expression DatabaseQuery =\n"
        "\t\tlet\n"
        '\t\t    database = Sql.Database("#{SQL_ENDPOINT}#", "#{WAREHOUSE}#")\n'
        "\t\tin\n"
        "\t\t    database\n"
        f"\tlineageTag: {tag('expression', 'DatabaseQuery')}\n",
        encoding="utf-8",
    )
    (DEF / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1604\n", encoding="utf-8")
    model_lines = [
        "model Model",
        f"\tculture: {model['culture']}",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        f"\tsourceQueryCulture: {model['culture']}",
        "",
        *[f"ref table {q(t)}" for t in table_names],
        "",
        *[f"ref role {q(r['name'])}" for r in model["roles"]],
        "",
        f"ref cultureInfo {model['culture']}",
        "",
    ]
    (DEF / "model.tmdl").write_text("\n".join(model_lines), encoding="utf-8")
    (DEF / "cultures" / f"{model['culture']}.tmdl").write_text(f"cultureInfo {model['culture']}\n", encoding="utf-8")
    (MODEL_DIR / ".platform").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "SemanticModel", "displayName": model["name"]},
                "config": {"version": "2.0", "logicalId": tag("item", "SemanticModel", model["name"])},
            },
            indent=2,
        )
        + "\n"
    )
    (MODEL_DIR / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2) + "\n")
    print(
        f"wrote {len(table_names)} tables, {len(model['measures']) + len(labels)} measures, {len(model['roles'])} roles"
    )


if __name__ == "__main__":
    main()
