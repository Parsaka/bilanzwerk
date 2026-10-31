"""Render the report scaffold (PBIR format) and powerbi/report-pages.md from report/pages.yml.

  python powerbi/tools/generate_report.py

Every page gets the parts that the spec fixes for all pages: the title that states the page's
question (bilingual measure from the Sprache table), a synced language slicer, the footer with
data cut-off and sources, and a grey build note that lists the main visuals for that page.
The main visuals themselves are placed in Power BI Desktop: their layout is design work that
has to be checked by eye against real data, so it is not generated. Delete the build note on a
page once its visuals are in place; a rerun of this script only recreates missing scaffolds and
never overwrites a page that has been edited (it skips pages whose folder already holds more
than the scaffold visuals).
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / "powerbi"
REPORT = PBI / "Bilanzwerk.Report"
DEF = REPORT / "definition"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
WIDTH, HEIGHT = 1280, 720
SCAFFOLD = {"titel", "sprache", "fusszeile", "bauplan"}

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
            "drawVisualContainerHeader": False,
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
            "drawVisualContainerHeader": False,
        },
    }


def build_note(page: dict, pos: dict) -> dict:
    lines = ["Bauplan (nach dem Platzieren der Visuals löschen):", *[f"• {v}" for v in page["visuals"]]]
    return {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.3.0/schema.json",
        "name": "bauplan",
        "position": pos,
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [
                    {
                        "properties": {
                            "paragraphs": [
                                {"textRuns": [{"value": line, "textStyle": {"fontSize": "11pt", "color": "#8C8C8C"}}]}
                                for line in lines
                            ]
                        }
                    }
                ]
            },
            "drawVisualContainerHeader": False,
        },
    }


def pos(x: int, y: int, w: int, h: int, z: int) -> dict:
    return {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def page_is_edited(page_dir: Path) -> bool:
    visuals = page_dir / "visuals"
    return visuals.exists() and any(p.name not in SCAFFOLD for p in visuals.iterdir())


def render_markdown(spec: dict) -> str:
    out = [
        "# Berichtsseiten / Report pages",
        "",
        "Generated from `powerbi/report/pages.yml` by `powerbi/tools/generate_report.py`. Each page answers one",
        "question, printed in its title. Title, language switch and footer are generated; the main visuals",
        "are placed in Power BI Desktop as listed here.",
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
        "Pages with a build note (`bauplan` visual) still need their main visuals. Screenshots of all 11 pages",
        "go to `docs/img/report/` once the report runs on real data.",
        "",
    ]
    return "\n".join(out)


def main(force: bool = False) -> None:
    spec = yaml.safe_load((PBI / "report" / "pages.yml").read_text(encoding="utf-8"))
    if force and DEF.exists():
        shutil.rmtree(DEF)

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

    names, created = [], 0
    for i, page in enumerate(spec["pages"], start=1):
        name = f"p{i:02d}_{page['id']}"
        names.append(name)
        page_dir = DEF / "pages" / name
        if page_is_edited(page_dir):
            continue
        write_json(
            page_dir / "page.json",
            {
                "$schema": f"{SCHEMA}/item/report/definition/page/1.3.0/schema.json",
                "name": name,
                "displayName": f"{i}. {page['de']['name']}",
                "displayOption": "FitToPage",
                "height": HEIGHT,
                "width": WIDTH,
            },
        )
        visuals = [
            measure_card("titel", f"Titel {i:02d}", pos(24, 12, 1060, 56, 0), 20, "#262626"),
            language_slicer(pos(1100, 16, 156, 48, 1)),
            build_note(page, pos(24, 88, 1232, 560, 2)),
            measure_card("fusszeile", "Fußzeile", pos(24, 676, 1232, 32, 3), 9, "#8C8C8C"),
        ]
        for v in visuals:
            write_json(page_dir / "visuals" / v["name"] / "visual.json", v)
        created += 1
    write_json(
        DEF / "pages" / "pages.json",
        {
            "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": names,
            "activePageName": names[0],
        },
    )
    (PBI / "report-pages.md").write_text(render_markdown(spec), encoding="utf-8")
    print(f"{len(names)} pages, {created} scaffolds written, {len(names) - created} edited pages kept")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
