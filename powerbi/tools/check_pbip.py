"""Static checks on the PBIP project that run on any CI runner (no Windows, no Power BI Desktop).

  python powerbi/tools/check_pbip.py            # exit 1 on any error

Two parts:
1. Model rules, mirroring the error-level rules in powerbi/bpa/rules.json (Tabular Editor runs
   the full rule set on the Windows job): every measure has a description, display folder and
   format string; foreign keys are hidden; every DAX reference resolves to a column or measure;
   relationship, RLS and OLS targets exist; no calculated columns (Direct Lake).
2. Report smoke test: the report has the 11 pages of the spec, each with title and footer, and
   every field a visual binds to exists in the model. Rendering a page needs the Power BI
   service; this test catches the broken bindings that would make a page fail to render.
3. Report files against Microsoft's published JSON schemas (vendored in powerbi/schemas, MIT
   licence, from github.com/microsoft/json-schemas), and the layout rules: every page has main
   visuals, every chart has a title, visuals stay on the 1280 x 720 canvas and do not overlap.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "powerbi" / "Bilanzwerk.SemanticModel" / "definition"
REPORT = ROOT / "powerbi" / "Bilanzwerk.Report" / "definition"
EXPECTED_PAGES = 11
SCHEMAS = ROOT / "powerbi" / "schemas"
SCHEMA_URL = "https://developer.microsoft.com/json-schemas/fabric/"
CANVAS = (1280, 720)
FRAME = {"titel", "sprache", "fusszeile"}

NAME = r"(?:'(?:[^']|'')+'|[^\s=']+)"
DAX_QUALIFIED = re.compile(r"(?:'((?:[^']|'')+)'|\b([A-Za-z_][\w\-]*))\[([^\]]+)\]")
DAX_BARE = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
DAX_STRING = re.compile(r'"(?:[^"]|"")*"')


def unquote(name: str) -> str:
    name = name.strip()
    if name.startswith("'") and name.endswith("'"):
        return name[1:-1].replace("''", "'")
    return name


@dataclass
class Measure:
    table: str
    name: str
    expression: str
    description: str = ""
    folder: str = ""
    format: str = ""


@dataclass
class Table:
    name: str
    columns: dict[str, dict] = field(default_factory=dict)
    measures: dict[str, Measure] = field(default_factory=dict)
    is_calc_group: bool = False


def parse_table(path: Path) -> Table:
    lines = path.read_text(encoding="utf-8").split("\n")
    table: Table | None = None
    doc: list[str] = []
    current: Measure | dict | None = None
    in_expr = False
    for line in lines:
        stripped = line.strip()
        depth = len(line) - len(line.lstrip("\t"))
        if stripped.startswith("///"):
            doc.append(stripped[3:].strip())
            continue
        if depth == 0 and stripped.startswith("table "):
            table = Table(unquote(stripped[6:]))
            doc = []
            continue
        assert table is not None, f"{path}: no table header"
        if depth == 1:
            in_expr = False
            m = re.match(rf"measure ({NAME})\s*=\s*(.*)$", stripped)
            if m:
                current = Measure(table.name, unquote(m.group(1)), m.group(2), description=" ".join(doc))
                table.measures[current.name] = current
                in_expr = True
            elif stripped.startswith("column "):
                m = re.match(rf"column ({NAME})(\s*=)?", stripped)
                current = {"name": unquote(m.group(1)), "hidden": False, "calculated": bool(m.group(2))}
                table.columns[current["name"]] = current
            elif stripped == "calculationGroup":
                table.is_calc_group = True
                current = None
            else:
                current = None
            doc = []
            continue
        if isinstance(current, Measure) and depth >= 2:
            key = stripped.split(":", 1)[0]
            if in_expr and depth >= 3:
                current.expression += "\n" + stripped
                continue
            in_expr = False
            if key == "formatString":
                current.format = stripped.split(":", 1)[1].strip()
            elif key == "displayFolder":
                current.folder = stripped.split(":", 1)[1].strip()
        elif isinstance(current, dict) and depth == 2 and stripped == "isHidden":
            current["hidden"] = True
    assert table is not None, f"{path}: empty"
    return table


def load_model() -> tuple[dict[str, Table], list[tuple[str, str, str, str]]]:
    tables = {t.name: t for t in (parse_table(p) for p in sorted((MODEL / "tables").glob("*.tmdl")))}
    rels = []
    text = (MODEL / "relationships.tmdl").read_text(encoding="utf-8")
    for frm, to in re.findall(r"fromColumn:\s*(\S+)\s*\n\s*toColumn:\s*(\S+)", text):
        ft, fc = frm.split(".", 1)
        tt, tc = to.split(".", 1)
        rels.append((unquote(ft), unquote(fc), unquote(tt), unquote(tc)))
    return tables, rels


def dax_references(expr: str) -> tuple[list[tuple[str, str]], list[str]]:
    expr = DAX_STRING.sub('""', expr)
    qualified = [(a or b, c) for a, b, c in DAX_QUALIFIED.findall(expr)]
    without = DAX_QUALIFIED.sub(" ", expr)
    return qualified, DAX_BARE.findall(without)


def check_model(tables: dict[str, Table], rels: list[tuple[str, str, str, str]]) -> list[str]:
    errors: list[str] = []
    measures = {m.name: m for t in tables.values() for m in t.measures.values()}
    all_columns = {c for t in tables.values() for c in t.columns}

    def resolve(expr: str, where: str) -> None:
        qualified, bare = dax_references(expr)
        for tbl, col in qualified:
            if tbl not in tables:
                errors.append(f"{where}: unknown table '{tbl}'")
            elif col not in tables[tbl].columns and col not in tables[tbl].measures:
                errors.append(f"{where}: unknown column or measure {tbl}[{col}]")
        for name in bare:
            if not (name in measures or name in all_columns or name.startswith("@")):
                errors.append(f"{where}: unknown reference [{name}]")

    for m in measures.values():
        where = f"measure [{m.name}]"
        if not m.description:
            errors.append(f"{where}: no description")
        if not m.folder:
            errors.append(f"{where}: no display folder")
        # text measures (titles, answer sentences) live in the folder Beschriftungen
        if not m.format and m.table != "Sprache" and not (m.folder or "").startswith("Beschriftungen"):
            errors.append(f"{where}: no format string")
        if re.search(r"\bIFERROR\s*\(", m.expression, re.IGNORECASE):
            errors.append(f"{where}: IFERROR (use DIVIDE or explicit checks)")
        resolve(m.expression, where)

    for t in tables.values():
        for c in t.columns.values():
            if c["calculated"]:
                errors.append(f"column {t.name}[{c['name']}]: calculated column (not supported on Direct Lake)")

    for ft, fc, tt, tc in rels:
        for tbl, col in ((ft, fc), (tt, tc)):
            if tbl not in tables or col not in tables[tbl].columns:
                errors.append(f"relationship {ft}.{fc} -> {tt}.{tc}: {tbl}.{col} does not exist")
        if ft in tables and fc in tables[ft].columns and not tables[ft].columns[fc]["hidden"]:
            errors.append(f"foreign key {ft}[{fc}] is visible (hide keys on the many side)")

    for path in sorted((MODEL / "roles").glob("*.tmdl")):
        text = path.read_text(encoding="utf-8")
        for raw, expr in re.findall(rf"tablePermission ({NAME}) = (.+)", text):
            tbl = unquote(raw)
            if tbl not in tables:
                errors.append(f"role {path.stem}: unknown table {tbl}")
                continue
            qualified, bare = dax_references(expr)
            for name in bare:
                if name not in tables[tbl].columns:
                    errors.append(f"role {path.stem}: {tbl}[{name}] does not exist")
            for qt, qc in qualified:
                if qt not in tables or qc not in tables[qt].columns:
                    errors.append(f"role {path.stem}: {qt}[{qc}] does not exist")
        current = None
        for line in text.split("\n"):
            m = re.match(rf"\ttablePermission ({NAME})\s*$", line)
            if m:
                current = unquote(m.group(1))
            m = re.match(rf"\t\tcolumnPermission ({NAME}) = ", line)
            if m and current and (current not in tables or unquote(m.group(1)) not in tables[current].columns):
                errors.append(f"role {path.stem}: OLS column {current}[{unquote(m.group(1))}] does not exist")

    date_file = MODEL / "tables" / "dim_date.tmdl"
    if not date_file.exists() or "\tdataCategory: Time" not in date_file.read_text(encoding="utf-8"):
        errors.append("model: dim_date is not marked as date table (dataCategory: Time)")
    return errors


def fields_in(obj: object) -> list[tuple[str, str]]:
    """All (entity, property) pairs a visual binds to."""
    found = []
    if isinstance(obj, dict):
        for kind in ("Measure", "Column"):
            if kind in obj and isinstance(obj[kind], dict) and "Property" in obj[kind]:
                ent = obj[kind].get("Expression", {}).get("SourceRef", {}).get("Entity")
                if ent:
                    found.append((ent, obj[kind]["Property"]))
        for v in obj.values():
            found += fields_in(v)
    elif isinstance(obj, list):
        for v in obj:
            found += fields_in(v)
    return found


def check_report(tables: dict[str, Table]) -> list[str]:
    errors: list[str] = []
    meta = json.loads((REPORT / "pages" / "pages.json").read_text(encoding="utf-8"))
    order = meta["pageOrder"]
    if len(order) != EXPECTED_PAGES:
        errors.append(f"report: {len(order)} pages, spec has {EXPECTED_PAGES}")
    for name in order:
        page_dir = REPORT / "pages" / name
        if not (page_dir / "page.json").exists():
            errors.append(f"page {name}: page.json missing")
            continue
        visuals = sorted((page_dir / "visuals").glob("*/visual.json"))
        names = {v.parent.name for v in visuals}
        for required in ("titel", "fusszeile"):
            if required not in names:
                errors.append(f"page {name}: no {required} visual")
        for v in visuals:
            data = json.loads(v.read_text(encoding="utf-8"))
            for ent, prop in fields_in(data.get("visual", {})):
                t = tables.get(ent)
                if t is None or (prop not in t.columns and prop not in t.measures):
                    errors.append(f"page {name}, visual {v.parent.name}: {ent}[{prop}] not in the model")
    return errors


def schema_errors() -> list[str]:
    """Every report JSON file against the schema its `$schema` names (local copies only)."""
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource

    def retrieve(uri: str) -> Resource:
        if not uri.startswith(SCHEMA_URL):
            raise LookupError(f"schema {uri} is not vendored")
        path = SCHEMAS / uri.removeprefix(SCHEMA_URL)
        return Resource.from_contents(json.loads(path.read_text(encoding="utf-8")))

    registry = Registry(retrieve=retrieve)
    errors = []
    for path in sorted(REPORT.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        uri = data.get("$schema", "")
        if not uri.startswith(SCHEMA_URL) or not (SCHEMAS / uri.removeprefix(SCHEMA_URL)).exists():
            errors.append(f"{path.relative_to(REPORT)}: schema {uri or '(none)'} is not vendored in powerbi/schemas")
            continue
        schema = registry.get_or_retrieve(uri).value.contents
        for e in Draft7Validator(schema, registry=registry).iter_errors(data):
            where = "/".join(str(p) for p in e.absolute_path)
            errors.append(f"{path.relative_to(REPORT)}: {where}: {e.message[:200]}")
    return errors


def layout_errors() -> list[str]:
    errors = []
    meta = json.loads((REPORT / "pages" / "pages.json").read_text(encoding="utf-8"))
    for name in meta["pageOrder"]:
        visuals = [
            json.loads(v.read_text(encoding="utf-8")) for v in (REPORT / "pages" / name).glob("visuals/*/visual.json")
        ]
        main = [v for v in visuals if v["name"] not in FRAME]
        if not main:
            errors.append(f"page {name}: no main visuals")
        boxes = []
        for v in visuals:
            p = v["position"]
            x0, y0, x1, y1 = p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]
            if x0 < 0 or y0 < 0 or x1 > CANVAS[0] or y1 > CANVAS[1]:
                errors.append(f"page {name}, visual {v['name']}: outside the {CANVAS[0]} x {CANVAS[1]} canvas")
            for other, (a0, b0, a1, b1) in boxes:
                if x0 < a1 and a0 < x1 and y0 < b1 and b0 < y1:
                    errors.append(f"page {name}: visuals {v['name']} and {other} overlap")
            boxes.append((v["name"], (x0, y0, x1, y1)))
            vis = v["visual"]
            is_headline = vis["visualType"] == "card" and "title" not in json.dumps(
                vis.get("visualContainerObjects", {})
            )
            titled = '"text"' in json.dumps(vis.get("visualContainerObjects", {}).get("title", []))
            if v["name"] not in FRAME and vis["visualType"] != "card" and not titled:
                errors.append(f"page {name}, visual {v['name']}: chart without a title")
            del is_headline
    return errors


def main() -> int:
    tables, rels = load_model()
    errors = check_model(tables, rels) + check_report(tables) + schema_errors() + layout_errors()
    n_measures = sum(len(t.measures) for t in tables.values())
    for e in errors:
        print(f"ERROR {e}")
    print(f"checked {len(tables)} tables, {n_measures} measures, {len(rels)} relationships: {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
