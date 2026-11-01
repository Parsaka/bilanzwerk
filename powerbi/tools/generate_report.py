"""Render the report (PBIR format) and powerbi/report-pages.md from report/pages.yml.

  python powerbi/tools/generate_report.py

Every page gets the parts that the spec fixes for all pages: the title that states the page's
question (bilingual measure from the Sprache table), a synced language slicer and the footer
with data cut-off and sources. The main visuals come from the page's `layout` in pages.yml
(tools/visuals.py builds the JSON). The report is generated as a whole: change the layout in
pages.yml and rerun, rather than editing the page in Power BI Desktop, so the next run does not
overwrite the change. What still needs Desktop is the look against real data (screenshots,
spacing) and the DAX Studio timings; see powerbi/README.md.
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_tmdl import label_name
from visuals import build

ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / "powerbi"
REPORT = PBI / "Bilanzwerk.Report"
DEF = REPORT / "definition"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
WIDTH, HEIGHT = 1280, 720

# Design rules (spec): one accent colour for the item the title talks about, grey for the rest,
# red and green only for risk bands.
THEME = {
    "name": "Bilanzwerk",
    "dataColors": ["#1F5AA6", "#8C8C8C", "#B3B3B3", "#5F5F5F", "#D0D0D0", "#737373", "#A6A6A6", "#404040"],
    "good": "#2E7D32",
    "neutral": "#F2B705",
    "bad": "#C62828",
    "maximum": "#1F5AA6",
    "center": "#D9D9D9",
    "minimum": "#FFFFFF",
    "foreground": "#262626",
    "background": "#FFFFFF",
    "tableAccent": "#1F5AA6",
    "textClasses": {
        "title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": "#262626"},
        "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": "#404040"},
        "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 24, "color": "#1F5AA6"},
        "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": "#262626"},
    },
}


def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def measure_card(name: str, measure: str, pos: dict, font_size: int, color: str) -> dict:
    return {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.3.0/schema.json",
        "name": name,
        "position": pos,
        "visual": {
            "visualType": "card",
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [
                            {
                                "field": {
                                    "Measure": {"Expression": {"SourceRef": {"Entity": "Sprache"}}, "Property": measure}
                                },
                                "queryRef": f"Sprache.{measure}",
                                "nativeQueryRef": measure,
                            }
                        ]
                    }
                }
            },
            "objects": {
                "labels": [
                    {"properties": {"fontSize": lit(f"{font_size}D"), "color": {"solid": {"color": lit(f"'{color}'")}}}}
                ],
                "categoryLabels": [{"properties": {"show": lit("false")}}],
            },
            "visualContainerObjects": {"visualHeader": [{"properties": {"show": lit("false")}}]},
        },
    }


def language_slicer(pos: dict) -> dict:
    return {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.3.0/schema.json",
        "name": "sprache",
        "position": pos,
        "visual": {
            "visualType": "slicer",
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [
                            {
                                "field": {
                                    "Column": {
                                        "Expression": {"SourceRef": {"Entity": "Sprache"}},
                                        "Property": "Sprache",
                                    }
                                },
                                "queryRef": "Sprache.Sprache",
                                "nativeQueryRef": "Sprache",
                                "active": True,
                            }
                        ]
                    }
                }
            },
            "objects": {
                "data": [{"properties": {"mode": lit("'Dropdown'")}}],
                "selection": [{"properties": {"strictSingleSelect": lit("true")}}],
                "header": [{"properties": {"show": lit("false")}}],
            },
            "syncGroup": {"groupName": "Sprache", "fieldChanges": True, "filterChanges": True},
            "visualContainerObjects": {"visualHeader": [{"properties": {"show": lit("false")}}]},
        },
    }


def pos(x: int, y: int, w: int, h: int, z: int) -> dict:
    return {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(spec: dict) -> str:
    out = [
        "# Berichtsseiten / Report pages",
        "",
        "Generated from `powerbi/report/pages.yml` by `powerbi/tools/generate_report.py`. Each page answers one",
        "question, printed in its title. The whole page is generated from `layout` in pages.yml: title,",
        "language switch, footer and the main visuals listed here.",
        "",
        "Design rules: one accent colour (#1F5AA6) for the item the title talks about, grey for the rest,",
        "red and green only for risk bands; every chart title states the finding (written after the real-data",
        "run, never before); a footer on each page with data cut-off date and source (measure `Fußzeile`).",
        "",
        "| # | Seite | Frage | Question | Main visuals | Measures |",
        "|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(spec["pages"], start=1):
        visuals = "<br>".join(p["visuals"])
        measures = ", ".join(f"`[{m}]`" for m in p["measures"])
        out.append(
            f"| {i} | {p['de']['name']} | {p['de']['question']} | {p['en']['question']} | {visuals} | {measures} |"
        )
    out += [
        "",
        "## Status",
        "",
        "All 11 pages carry their main visuals (generated, checked against the Microsoft PBIR schemas and",
        "the model by `check_pbip.py`). Open in Power BI Desktop: screenshots of all 11 pages for",
        "`docs/img/report/` and the DAX Studio timings, both against the deployed model.",
        "",
    ]
    return "\n".join(out)


def main() -> None:
    spec = yaml.safe_load((PBI / "report" / "pages.yml").read_text(encoding="utf-8"))
    model = yaml.safe_load((PBI / "model.yml").read_text(encoding="utf-8"))
    units = {m["name"]: m["unit"] for m in model["measures"] if "unit" in m}

    write_json(
        PBI / "Bilanzwerk.pbip",
        {
            "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": "Bilanzwerk.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )
    write_json(
        REPORT / "definition.pbir",
        {
            "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../Bilanzwerk.SemanticModel"}},
        },
    )
    write_json(
        REPORT / ".platform",
        {
            "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Report", "displayName": "Bilanzwerk"},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, "bilanzwerk/report"))},
        },
    )
    write_json(
        DEF / "version.json",
        {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"},
    )
    write_json(
        DEF / "report.json",
        {
            "$schema": f"{SCHEMA}/item/report/definition/report/1.2.0/schema.json",
            "layoutOptimization": "None",
            "themeCollection": {
                "customTheme": {
                    "name": "Bilanzwerk.json",
                    "reportVersionAtImport": "5.61",
                    "type": "RegisteredResources",
                }
            },
            "resourcePackages": [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [{"name": "Bilanzwerk.json", "path": "Bilanzwerk.json", "type": "CustomTheme"}],
                }
            ],
            "settings": {
                "useStylableVisualContainerHeader": True,
                "defaultDrillFilterOtherVisuals": True,
                "allowChangeFilterTypes": True,
                "useEnhancedTooltips": True,
            },
        },
    )
    write_json(REPORT / "StaticResources" / "RegisteredResources" / "Bilanzwerk.json", THEME)

    names = []
    for i, page in enumerate(spec["pages"], start=1):
        name = f"p{i:02d}_{page['id']}"
        names.append(name)
        page_dir = DEF / "pages" / name
        if page_dir.exists():
            shutil.rmtree(page_dir)
        page_json = {
            "$schema": f"{SCHEMA}/item/report/definition/page/1.3.0/schema.json",
            "name": name,
            "displayName": f"{i}. {page['de']['name']}",
            "displayOption": "FitToPage",
            "height": HEIGHT,
            "width": WIDTH,
        }
        # a slicer with `filters_only` filters just those visuals (e.g. the fiscal year drives the
        # waterfall of one year, not the charts "je Geschäftsjahr" next to it)
        interactions = [
            {"source": v["name"], "target": other["name"], "type": "NoFilter"}
            for v in page.get("layout", [])
            if "filters_only" in v
            for other in page["layout"]
            if other["name"] != v["name"] and other["name"] not in v["filters_only"] and other["type"] != "slicer"
        ]
        if interactions:
            page_json["visualInteractions"] = interactions
        write_json(page_dir / "page.json", page_json)
        visuals = [
            measure_card("titel", f"Titel {i:02d}", pos(24, 12, 1060, 56, 0), 20, "#262626"),
            language_slicer(pos(1100, 16, 156, 48, 1)),
            measure_card("fusszeile", "Fußzeile", pos(24, 676, 1232, 32, 2), 9, "#8C8C8C"),
        ]
        for z, v in enumerate(page.get("layout", []), start=len(visuals)):
            entry = dict(v)
            if "label" in entry and "title" not in entry:
                entry["title"] = f"Sprache.[{label_name(i, v['name'])}]"
            visuals.append(build(entry, z, units))
        for v in visuals:
            write_json(page_dir / "visuals" / v["name"] / "visual.json", v)
    write_json(
        DEF / "pages" / "pages.json",
        {
            "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": names,
            "activePageName": names[0],
        },
    )
    (PBI / "report-pages.md").write_text(render_markdown(spec), encoding="utf-8")
    print(f"{len(names)} pages written")


if __name__ == "__main__":
    main()
