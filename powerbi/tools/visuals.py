"""Building blocks for PBIR visuals (visualContainer 1.3.0), used by generate_report.py.

A visual in report/pages.yml names its fields as `table.column` or `table.[Measure]`. This module
turns that into the query projections, sort, filters and formatting objects Power BI expects,
so a page layout is reviewed as a short YAML entry and not as 200 lines of generated JSON.
The output is validated against the vendored Microsoft schemas (powerbi/schemas) by
check_pbip.py.
"""

from __future__ import annotations

import re

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
VISUAL_SCHEMA = f"{SCHEMA}/item/report/definition/visualContainer/1.3.0/schema.json"
FIELD = re.compile(r"^(?P<table>[^.\[]+(?: [^.\[]+)*)\.(?:\[(?P<measure>.+)\]|(?P<column>.+))$")

# Query roles per visual type (the names Power BI uses in queryState).
ROLES = {
    "card": ["Values"],
    "slicer": ["Values"],
    "tableEx": ["Values"],
    "pivotTable": ["Rows", "Columns", "Values"],
    "clusteredBarChart": ["Category", "Series", "Y"],
    "clusteredColumnChart": ["Category", "Series", "Y"],
    "columnChart": ["Category", "Series", "Y"],
    "barChart": ["Category", "Series", "Y"],
    "lineChart": ["Category", "Series", "Y"],
    "waterfallChart": ["Category", "Breakdown", "Y"],
    "scatterChart": ["Category", "Series", "X", "Y", "Size"],
}
CHARTS = {t for t in ROLES if t.endswith("Chart")}
# Display units: amounts are EUR measures with `unit: Mio|Mrd` in model.yml, shown in that unit;
# everything else (counts, days, ratios) without automatic scaling, which would print "1,3T".
UNITS = {"Mio": "1000000D", "Mrd": "1000000000D"}
CATEGORY_ROLES = {"Category", "Series", "Rows", "Columns", "Breakdown"}


def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def text(value: str) -> dict:
    return lit("'" + value.replace("'", "''") + "'")


def parse(ref: str) -> tuple[str, str, str]:
    """`table.[Measure]` -> (table, Measure, "Measure"); `table.column` -> (table, column, "Column")."""
    m = FIELD.match(ref)
    if not m:
        raise ValueError(f"field reference {ref!r} is not table.column or table.[Measure]")
    if m.group("measure"):
        return m.group("table"), m.group("measure"), "Measure"
    return m.group("table"), m.group("column"), "Column"


def field(ref: str, source: str | None = None) -> dict:
    """The field expression; `source` uses a filter's alias instead of the entity name."""
    table, prop, kind = parse(ref)
    expr = {"SourceRef": {"Source": source}} if source else {"SourceRef": {"Entity": table}}
    return {kind: {"Expression": expr, "Property": prop}}


def query_ref(ref: str) -> str:
    table, prop, _ = parse(ref)
    return f"{table}.{prop}"


def projection(ref: str, active: bool = False, name: str | None = None) -> dict:
    out = {"field": field(ref), "queryRef": query_ref(ref), "nativeQueryRef": parse(ref)[1]}
    if name:
        # what headers, axis titles and legends show instead of the column or measure name
        out["displayName"] = name
    if active:
        out["active"] = True
    return out


def measure_expr(ref: str) -> dict:
    return {"expr": field(ref)}


def categorical_filter(name: str, ref: str, values: list[str]) -> dict:
    """Visual-level filter: column in (values)."""
    table, _, _ = parse(ref)
    alias = "f"
    return {
        "name": name,
        "field": field(ref),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [field(ref, alias)],
                            "Values": [[{"Literal": {"Value": "'" + v.replace("'", "''") + "'"}}] for v in values],
                        }
                    }
                }
            ],
        },
        "howCreated": "User",
    }


def not_blank_filter(name: str, ref: str) -> dict:
    """Visual-level filter: column is not blank. Keeps the engine's blank member (facts without a
    dimension row) out of a single-select slicer, which would otherwise preselect it."""
    table, _, _ = parse(ref)
    alias = "f"
    return {
        "name": name,
        "field": field(ref),
        "type": "Advanced",
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "Not": {
                            "Expression": {
                                "Comparison": {
                                    "ComparisonKind": 0,
                                    "Left": field(ref, alias),
                                    "Right": {"Literal": {"Value": "null"}},
                                }
                            }
                        }
                    }
                }
            ],
        },
        "howCreated": "User",
    }


def selection(ref: str, value: str) -> dict:
    """A slicer's saved selection: the member it shows when the report opens."""
    table, _, _ = parse(ref)
    # integers (fiscal_year) are Int64 literals, everything else a string
    literal = f"{value}L" if re.fullmatch(r"-?\d+", str(value)) else "'" + str(value).replace("'", "''") + "'"
    return {
        "filter": {
            "Version": 2,
            "From": [{"Name": "s", "Entity": table, "Type": 0}],
            "Where": [
                {"Condition": {"In": {"Expressions": [field(ref, "s")], "Values": [[{"Literal": {"Value": literal}}]]}}}
            ],
        }
    }


def top_n_filter(name: str, ref: str, by: str, n: int) -> dict:
    """Visual-level Top N filter: the n members of `ref` with the largest `by`."""
    table, _, _ = parse(ref)
    by_table, _, _ = parse(by)
    entities = {table: "d"}
    if by_table not in entities:
        entities[by_table] = "m"
    sub_from = [{"Name": alias, "Entity": ent, "Type": 0} for ent, alias in entities.items()]
    return {
        "name": name,
        "field": field(ref),
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [
                {
                    "Name": "subquery",
                    "Expression": {
                        "Subquery": {
                            "Query": {
                                "Version": 2,
                                "From": sub_from,
                                "Select": [{**field(ref, entities[table]), "Name": "field"}],
                                "OrderBy": [{"Direction": 2, "Expression": field(by, entities[by_table])}],
                                "Top": n,
                            }
                        }
                    },
                    "Type": 2,
                },
                {"Name": "d", "Entity": table, "Type": 0},
            ],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [field(ref, "d")],
                            "Table": {"SourceRef": {"Source": "subquery"}},
                        }
                    }
                }
            ],
        },
        "howCreated": "User",
    }


def display_units(refs: list[str], units: dict[str, str]) -> dict:
    """The display units literal for these value fields: their unit if they have one, else none."""
    found = [units[parse(r)[1]] for r in refs if parse(r)[2] == "Measure" and parse(r)[1] in units]
    return lit(UNITS[found[0]] if found else "1D")


def build(spec: dict, z: int, units: dict[str, str] | None = None, names: dict[str, str] | None = None) -> dict:
    """One visual from its pages.yml entry; `units` maps measure names to Mio/Mrd (model.yml)."""
    units = units or {}
    # display names: the report-wide map (pages.yml field_names), overridden per visual (names)
    names = {**(names or {}), **spec.get("names", {})}
    vtype = spec["type"]
    x, y, w, h = spec["pos"]
    visual: dict = {"visualType": vtype}

    roles = spec.get("fields", {})
    unknown = set(roles) - set(ROLES.get(vtype, []))
    if unknown:
        raise ValueError(f"{spec['name']}: roles {sorted(unknown)} not valid for {vtype}")
    if roles:
        state = {
            role: {"projections": [projection(r, active=(vtype == "slicer"), name=names.get(r)) for r in refs]}
            for role, refs in roles.items()
        }
        query: dict = {"queryState": state}
        if "sort" in spec:
            ref, direction = spec["sort"]
            query["sortDefinition"] = {
                "sort": [{"field": field(ref), "direction": "Descending" if direction == "desc" else "Ascending"}],
                "isDefaultSort": True,
            }
        visual["query"] = query

    values = [r for role, refs in roles.items() if role not in CATEGORY_ROLES | {"X"} for r in refs]
    objects: dict = {}
    if vtype == "slicer":
        mode = spec.get("slicer_mode", "Dropdown")
        objects["data"] = [{"properties": {"mode": text(mode)}}]
        if spec.get("single_select", True):
            objects["selection"] = [{"properties": {"strictSingleSelect": lit("true")}}]
        if "default" in spec:
            objects["general"] = [{"properties": {"filter": selection(spec["fields"]["Values"][0], spec["default"])}}]
        # the visual title names the field already; the header would only repeat the column name
        objects["header"] = [{"properties": {"show": lit("false")}}]
    if vtype == "card":
        objects["labels"] = [
            {
                "properties": {
                    "fontSize": lit(f"{spec.get('font_size', 24)}D"),
                    "labelDisplayUnits": display_units(values, units),
                }
            }
        ]
        objects["categoryLabels"] = [{"properties": {"show": lit("false")}}]
        if spec.get("word_wrap"):
            objects["wordWrap"] = [{"properties": {"show": lit("true")}}]
    if vtype in ("tableEx", "pivotTable"):
        objects["values"] = [{"properties": {"wordWrap": lit("true")}}]
        objects["columnHeaders"] = [{"properties": {"wordWrap": lit("true")}}]
        if "conditional_back" in spec:
            # background of one column from a colour measure (red/yellow/green only for risk bands)
            target, colour = spec["conditional_back"]
            objects["values"].append(
                {
                    "properties": {"backColor": {"solid": {"color": measure_expr(colour)}}},
                    "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": query_ref(target)},
                }
            )
        scaled = [r for r in values if parse(r)[2] == "Measure" and parse(r)[1] in units]
        if scaled:
            objects["columnFormatting"] = [
                {"properties": {"labelDisplayUnits": display_units([r], units)}, "selector": {"metadata": query_ref(r)}}
                for r in scaled
            ]
        if spec.get("widths"):
            objects["columnWidth"] = [
                {"properties": {"value": lit(f"{px}D")}, "selector": {"metadata": query_ref(ref)}}
                for ref, px in spec["widths"].items()
            ]
    if vtype == "tableEx":
        # a total over companies, hypotheses or rules means nothing here
        objects["total"] = [{"properties": {"totals": lit("false")}}]
    if "colour_by" in spec:
        # one accent colour for the item the title talks about, grey for the rest
        objects["dataPoint"] = [
            {
                "properties": {"fill": {"solid": {"color": measure_expr(spec["colour_by"])}}},
                "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]},
            }
        ]
    if spec.get("data_labels"):
        objects["labels"] = [{"properties": {"show": lit("true")}}]
    if vtype in CHARTS:
        unit = display_units(values, units)
        objects.setdefault("labels", [{"properties": {}}])[0]["properties"]["labelDisplayUnits"] = unit
        objects["valueAxis"] = [{"properties": {"labelDisplayUnits": unit}}]
        if vtype == "scatterChart":
            objects["categoryAxis"] = [{"properties": {"labelDisplayUnits": display_units(roles.get("X", []), units)}}]
        if "Series" in roles:
            objects["legend"] = [{"properties": {"showTitle": lit("false")}}]
        # long category names (sectors, model names): up to `label_space` % of the width for the
        # labels instead of cutting them; `category_width` lets all categories fit without a scrollbar
        axis = objects.setdefault("categoryAxis", [{"properties": {}}])[0]["properties"]
        if "label_space" in spec:
            axis["maxMarginFactor"] = lit(f"{spec['label_space']}L")
        if "category_width" in spec:
            axis["minCategoryWidth"] = lit(f"{spec['category_width']}D")
        if not axis:
            del objects["categoryAxis"]
    if objects:
        visual["objects"] = objects

    title = spec.get("title")
    container: dict = {}
    if title:
        # findings are sentences; wrapped instead of cut off with "...". Not on slicers: their box is one
        # line high and a second title line would push the dropdown out of it.
        wrap = "false" if vtype == "slicer" else "true"
        container["title"] = [
            {"properties": {"show": lit("true"), "text": measure_expr(title), "titleWrap": lit(wrap)}}
        ]
    else:
        container["title"] = [{"properties": {"show": lit("false")}}]
    visual["visualContainerObjects"] = container
    if vtype == "slicer" and spec.get("sync_group"):
        visual["syncGroup"] = {"groupName": spec["sync_group"], "fieldChanges": True, "filterChanges": True}

    out = {
        "$schema": VISUAL_SCHEMA,
        "name": spec["name"],
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
        "visual": visual,
    }
    filters = []
    if vtype == "slicer" and spec.get("single_select", True):
        filters.append(not_blank_filter("nb", spec["fields"]["Values"][0]))
    for i, flt in enumerate(spec.get("filters", [])):
        if "top" in flt:
            filters.append(top_n_filter(f"f{i}", flt["field"], flt["by"], flt["top"]))
        elif flt.get("not_blank"):
            filters.append(not_blank_filter(f"f{i}", flt["field"]))
        else:
            filters.append(categorical_filter(f"f{i}", flt["field"], flt["in"]))
    if filters:
        out["filterConfig"] = {"filters": filters}
    return out


def fields_of(spec: dict) -> list[str]:
    """Every field reference in a visual entry (for the label check in generate_report)."""
    refs = [r for refs in spec.get("fields", {}).values() for r in refs]
    refs += [f["field"] for f in spec.get("filters", [])] + [f["by"] for f in spec.get("filters", []) if "by" in f]
    for key in ("title", "colour_by"):
        if key in spec:
            refs.append(spec[key])
    if "sort" in spec:
        refs.append(spec["sort"][0])
    if "conditional_back" in spec:
        refs += list(spec["conditional_back"])
    return refs
