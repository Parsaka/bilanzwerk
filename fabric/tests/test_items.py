"""Fabric items: valid files, unique logical IDs, and every reference points at an item in the repo."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ITEMS = sorted(
    [
        *ROOT.glob("fabric/*.Notebook"),
        *ROOT.glob("fabric/*.DataPipeline"),
        *ROOT.glob("powerbi/*.SemanticModel"),
        *ROOT.glob("powerbi/*.Report"),
    ]
)
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
ZERO = "00000000-0000-0000-0000-000000000000"


def platform(item: Path) -> dict:
    return json.loads((item / ".platform").read_text(encoding="utf-8"))


def logical_ids() -> dict[str, str]:
    return {platform(i)["config"]["logicalId"]: i.name for i in ITEMS}


def test_every_item_has_a_platform_file_with_matching_type_and_name():
    assert len(ITEMS) >= 10
    for item in ITEMS:
        meta = platform(item)["metadata"]
        name, kind = item.name.rsplit(".", 1)
        assert meta["type"] == kind, item
        assert meta["displayName"] == name, item


def test_logical_ids_are_unique():
    ids = [platform(i)["config"]["logicalId"] for i in ITEMS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("pipeline", sorted(ROOT.glob("fabric/*.DataPipeline")), ids=lambda p: p.name)
def test_pipeline_references_resolve(pipeline):
    text = (pipeline / "pipeline-content.json").read_text(encoding="utf-8")
    doc = json.loads(text)
    known = logical_ids()
    for guid in set(GUID.findall(text)) - {ZERO}:
        assert guid in known, f"{pipeline.name} references unknown item {guid}"
    # Parameters used in expressions are declared.
    declared = set(doc["properties"].get("parameters", {}))
    used = set(re.findall(r"pipeline\(\)\.parameters\.(\w+)", text))
    assert used <= declared, f"{pipeline.name}: undeclared parameters {used - declared}"


def test_pipeline_alerts_have_a_single_dependency():
    # Several dependencies are AND-ed in Fabric: an alert on "A failed and B failed" never fires.
    for path in ROOT.glob("fabric/*.DataPipeline/pipeline-content.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        stack = list(doc["properties"]["activities"])
        while stack:
            act = stack.pop()
            stack += act.get("typeProperties", {}).get("ifTrueActivities", [])
            if act["type"] == "Office365Outlook":
                assert len(act["dependsOn"]) <= 1, f"{path.parent.name}: {act['name']}"


@pytest.mark.parametrize("notebook", sorted(ROOT.glob("fabric/*.Notebook")), ids=lambda p: p.name)
def test_notebook_source_parses(notebook):
    src = (notebook / "notebook-content.py").read_text(encoding="utf-8")
    assert src.startswith("# Fabric notebook source")
    assert "# PARAMETERS CELL" in src
    ast.parse("\n".join(line for line in src.splitlines() if not line.startswith("%")))
