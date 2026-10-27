"""The PBIP checker must pass on the generated project and catch the mistakes it is there for."""

from __future__ import annotations

import importlib.util
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
    return check.check_model(tables, rels) + check.check_report(tables)


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
