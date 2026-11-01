"""Visual building blocks: display units from model.yml, slicers that cannot open on BLANK."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

PBI = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, PBI / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def units_of(visual: dict) -> list[str]:
    return re.findall(r'"labelDisplayUnits": \{"expr": \{"Literal": \{"Value": "([^"]+)"', json.dumps(visual))


def test_amounts_show_in_their_unit_and_counts_without_scaling():
    v = load("visuals")
    units = {"Cash-Potenzial aktuell": "Mrd", "Umsatz": "Mio"}
    card = v.build(
        {"name": "c", "type": "card", "pos": [0, 0, 1, 1], "fields": {"Values": ["t.[Cash-Potenzial aktuell]"]}},
        0,
        units,
    )
    count = v.build(
        {"name": "n", "type": "card", "pos": [0, 0, 1, 1], "fields": {"Values": ["t.[Insolvenzen]"]}}, 0, units
    )
    bars = v.build(
        {"name": "b", "type": "barChart", "pos": [0, 0, 1, 1], "fields": {"Category": ["s.name"], "Y": ["t.[Umsatz]"]}},
        0,
        units,
    )
    table = v.build(
        {"name": "t", "type": "tableEx", "pos": [0, 0, 1, 1], "fields": {"Values": ["s.name", "t.[Umsatz]"]}}, 0, units
    )
    assert units_of(card) == ["1000000000D"]
    assert units_of(count) == ["1D"]
    assert set(units_of(bars)) == {"1000000D"}  # data labels and value axis
    assert table["visual"]["objects"]["columnFormatting"][0]["selector"] == {"metadata": "t.Umsatz"}


def test_model_amounts_have_no_scaling_commas_and_a_known_unit():
    model = yaml.safe_load((PBI / "model.yml").read_text(encoding="utf-8"))
    for m in model["measures"]:
        # Power BI prints the commas of "#,0,," literally instead of scaling
        assert ",," not in m.get("format", ""), m["name"]
        assert m.get("unit", "Mio") in {"Mio", "Mrd"}, m["name"]


def test_single_select_slicer_excludes_blank_and_opens_on_its_default():
    v = load("visuals")
    slicer = v.build(
        {
            "name": "u",
            "type": "slicer",
            "pos": [0, 0, 1, 1],
            "fields": {"Values": ["dim_company.company_name"]},
            "default": "ACME",
        },
        0,
    )
    (flt,) = slicer["filterConfig"]["filters"]
    assert flt["type"] == "Advanced" and "Not" in flt["filter"]["Where"][0]["Condition"]
    saved = slicer["visual"]["objects"]["general"][0]["properties"]["filter"]["filter"]
    assert saved["Where"][0]["Condition"]["In"]["Values"] == [[{"Literal": {"Value": "'ACME'"}}]]
    year = v.selection("dim_period.fiscal_year", "2025")["filter"]
    assert year["Where"][0]["Condition"]["In"]["Values"] == [[{"Literal": {"Value": "2025L"}}]]


def test_field_parameter_value_measure_switches_on_the_order_column():
    gen = load("generate_tmdl")
    fp = {"name": "KPI-X", "measures": ["DSO", "Z'' Score"]}
    tmdl = gen.render_field_parameter(fp, {"DSO": "f", "Z'' Score": "f"})
    want = "measure 'KPI-X Wert' = SWITCH ( SELECTEDVALUE ( 'KPI-X'[KPI-X Reihenfolge] ), 0, [DSO], 1, [Z'' Score] )"
    assert want in tmdl


def test_field_parameter_value_is_blank_outside_its_bounds():
    gen = load("generate_tmdl")
    fp = {"name": "KPI-X", "measures": ["DSO", "CCC"], "bounds": {"DSO": [0, 730]}}
    tmdl = gen.render_field_parameter(fp, {"DSO": "f", "CCC": "f"})
    assert "0, VAR _v = [DSO] RETURN IF ( _v >= 0 && _v <= 730, _v ), 1, [CCC] )" in tmdl
    model = yaml.safe_load((PBI / "model.yml").read_text(encoding="utf-8"))
    for fp in model["field_parameters"]:
        assert set(fp["bounds"]) == set(fp["measures"]), fp["name"]


def test_field_parameter_percentile_uses_the_kpi_code_of_the_selected_measure():
    gen = load("generate_tmdl")
    fp = {"name": "KPI-X", "measures": ["DSO", "Verschuldungsgrad"], "kpi_codes": {"DSO": "DSO"}}
    tmdl = gen.render_field_parameter(fp, {"DSO": "f", "Verschuldungsgrad": "f"})
    want = 'Reihenfolge] ), 0, CALCULATE ( [Sektorperzentil], dim_kpi[kpi_code] = "DSO" ) )'
    assert "measure 'KPI-X Perzentil' = SWITCH" in tmdl and want in tmdl  # no code: no branch, BLANK


def test_tables_have_widths_and_no_meaningless_total():
    v = load("visuals")
    spec = {
        "name": "t",
        "type": "tableEx",
        "pos": [0, 0, 1, 1],
        "fields": {"Values": ["s.name", "t.[Wert]"]},
        "widths": {"s.name": 200, "t.[Wert]": 80},
    }
    objects = v.build(spec, 0)["visual"]["objects"]
    assert objects["total"] == [{"properties": {"totals": {"expr": {"Literal": {"Value": "false"}}}}}]
    assert [w["selector"]["metadata"] for w in objects["columnWidth"]] == ["s.name", "t.Wert"]


def test_year_slicer_filters_only_the_visuals_of_that_year():
    import json

    report = PBI / "Bilanzwerk.Report" / "definition" / "pages" / "p04_guv" / "page.json"
    interactions = json.loads(report.read_text(encoding="utf-8"))["visualInteractions"]
    targets = {(i["source"], i["target"]) for i in interactions if i["type"] == "NoFilter"}
    assert ("geschaeftsjahr", "umsatz_bis_ebit") in targets and ("geschaeftsjahr", "margen") in targets
    assert ("geschaeftsjahr", "bruecke") not in targets
