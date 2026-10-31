"""The PBIP checker must pass on the generated project and catch the mistakes it is there for."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path, monkeypatch):
    check = load("check_pbip")
    src = Path(check.ROOT) / "powerbi"
    shutil.copytree(src / "Bilanzwerk.SemanticModel", tmp_path / "Bilanzwerk.SemanticModel")
    shutil.copytree(src / "Bilanzwerk.Report", tmp_path / "Bilanzwerk.Report")
    monkeypatch.setattr(check, "MODEL", tmp_path / "Bilanzwerk.SemanticModel" / "definition")
    monkeypatch.setattr(check, "REPORT", tmp_path / "Bilanzwerk.Report" / "definition")
    return check, tmp_path


def errors(check) -> list[str]:
    tables, rels = check.load_model()
    return check.check_model(tables, rels) + check.check_report(tables) + check.schema_errors() + check.layout_errors()


def test_generated_project_is_clean(project):
    check, _ = project
    tables, rels = check.load_model()
    assert len(tables) >= 20 and len(rels) >= 15
    assert sum(len(t.measures) for t in tables.values()) >= 50
    assert errors(check) == []


def test_unknown_column_in_measure_is_an_error(project):
    check, root = project
    path = root / "Bilanzwerk.SemanticModel" / "definition" / "tables" / "fact_kpi.tmdl"
    path.write_text(
        path.read_text(encoding="utf-8").replace("fact_kpi[sector_percentile]", "fact_kpi[percentil]"), encoding="utf-8"
    )
    assert any("fact_kpi[percentil]" in e for e in errors(check))


def test_measure_without_description_is_an_error(project):
    check, root = project
    path = root / "Bilanzwerk.SemanticModel" / "definition" / "tables" / "fact_kpi.tmdl"
    text = path.read_text(encoding="utf-8")
    text = text.replace("\t/// Perzentil der Kennzahl innerhalb von Sektor und Jahr.\n", "")
    path.write_text(text, encoding="utf-8")
    assert "measure [Sektorperzentil]: no description" in errors(check)


def test_visible_foreign_key_is_an_error(project):
    check, root = project
    path = root / "Bilanzwerk.SemanticModel" / "definition" / "tables" / "dim_company.tmdl"
    lines = path.read_text(encoding="utf-8").split("\n")
    start = lines.index("\tcolumn sector_key")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("\tcolumn"))
    lines[start:end] = [line for line in lines[start:end] if line.strip() != "isHidden"]
    path.write_text("\n".join(lines), encoding="utf-8")
    assert any("dim_company[sector_key] is visible" in e for e in errors(check))


def test_visual_bound_to_missing_measure_is_an_error(project):
    check, root = project
    visual = next((root / "Bilanzwerk.Report" / "definition" / "pages").glob("p01_*/visuals/titel/visual.json"))
    visual.write_text(visual.read_text(encoding="utf-8").replace("Titel 01", "Titel 99"), encoding="utf-8")
    assert any("Sprache[Titel 99] not in the model" in e for e in errors(check))


def test_property_outside_the_microsoft_schema_is_an_error(project):
    check, root = project
    visual = next((root / "Bilanzwerk.Report" / "definition" / "pages").glob("p09_*/visuals/bruecke/visual.json"))
    data = json.loads(visual.read_text(encoding="utf-8"))
    data["visual"]["drawVisualContainerHeader"] = False
    visual.write_text(json.dumps(data), encoding="utf-8")
    assert any("bruecke" in e and "drawVisualContainerHeader" in e for e in errors(check))


def test_overlapping_visuals_are_an_error(project):
    check, root = project
    visual = next((root / "Bilanzwerk.Report" / "definition" / "pages").glob("p09_*/visuals/top20/visual.json"))
    data = json.loads(visual.read_text(encoding="utf-8"))
    data["position"]["x"] = 100
    visual.write_text(json.dumps(data), encoding="utf-8")
    assert any("top20" in e and "overlap" in e for e in errors(check))


def test_every_page_has_main_visuals_with_titles(project):
    check, root = project
    pages = sorted((root / "Bilanzwerk.Report" / "definition" / "pages").glob("p*_*"))
    assert len(pages) == 11
    for page in pages:
        names = {v.parent.name for v in page.glob("visuals/*/visual.json")}
        assert names - check.FRAME, f"{page.name} has no main visuals"


def test_layout_field_references_are_parsed():
    visuals = load("visuals")
    assert visuals.parse("fact_kpi.[Z'' Score]") == ("fact_kpi", "Z'' Score", "Measure")
    assert visuals.parse("KPI-Auswahl Y.KPI-Auswahl Y") == ("KPI-Auswahl Y", "KPI-Auswahl Y", "Column")
    with pytest.raises(ValueError):
        visuals.parse("no_table")


def test_bpa_rule_expressions_parse_in_tabular_editor():
    """Tabular Editor's expression parser takes string literals verbatim: a doubled backslash
    reaches the regex as two characters, and a backslash-escaped quote ends the string."""
    import json
    import re

    rules = json.loads((TOOLS.parent / "bpa" / "rules.json").read_text(encoding="utf-8"))
    for rule in rules:
        expr = rule["Expression"]
        assert "\\\\" not in expr and '\\"' not in expr, rule["ID"]
        for literal in re.findall(r'RegEx\.IsMatch\(Expression, "([^"]*)"\)', expr):
            re.compile(literal)
