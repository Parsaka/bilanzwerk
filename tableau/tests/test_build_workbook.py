"""The Tableau package must hold well-formed XML and a title computed from the packaged data."""

from __future__ import annotations

import csv
import importlib.util
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("build_workbook", ROOT / "tableau" / "build_workbook.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_workbook"] = module
    spec.loader.exec_module(module)
    return module


def write_extract(path: Path, rows: list[dict]) -> None:
    bw = load()
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(bw.COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, 1) for c in bw.COLUMNS})


def test_finding_uses_the_latest_fiscal_year_per_company(tmp_path):
    bw = load()
    rows = [
        {"company_name": "A", "cik": 1, "sector_de": "Handel", "fiscal_year": 2023, "cash_opportunity_eur": 9e9},
        {"company_name": "A", "cik": 1, "sector_de": "Handel", "fiscal_year": 2024, "cash_opportunity_eur": 1e9},
        {"company_name": "B", "cik": 2, "sector_de": "Energie", "fiscal_year": 2024, "cash_opportunity_eur": 2e9},
    ]
    path = tmp_path / "wc.csv"
    write_extract(path, rows)
    f = bw.finding(bw.read_extract(path))
    assert f["top_sector"] == "Energie"  # A's older 9 bn does not count
    assert abs(f["total_eur_bn"] - 3.0) < 1e-9


def test_workbook_opens_on_the_dashboard_and_reads_the_extract():
    bw = load()
    f = {"top_sector": "Energie", "top_eur_bn": 2.0, "total_eur_bn": 3.0, "years": (2020, 2024)}
    root = ET.fromstring(bw.build_twb(f))
    # Tableau refuses a workbook without an active window and Tableau Public one without an extract
    windows = {w.get("name"): w for w in root.find("windows")}
    assert set(windows) == {*bw.SHEETS, bw.DASHBOARD}
    assert windows[bw.DASHBOARD].get("class") == "dashboard"
    assert windows[bw.DASHBOARD].find("active") is not None
    assert all(windows[n].find("cards") is not None for n in bw.SHEETS)
    extract = root.find(".//datasource[@name='federated.bilanzwerk_wc']/extract")
    assert extract.get("enabled") == "true"
    assert extract.find("connection").get("dbname") == bw.HYPER_PATH
    layout = root.find(".//datasource[@name='federated.bilanzwerk_wc']/layout")
    assert layout.get("dim-percentage") and layout.get("measure-percentage")


def test_package_holds_parseable_workbook_and_the_data(tmp_path, monkeypatch):
    pytest.importorskip("tableauhyperapi")
    bw = load()
    path = tmp_path / "wc.csv"
    write_extract(
        path,
        [
            {"company_name": "B", "cik": 2, "sector_de": "Energie", "fiscal_year": 2024},
            {"company_name": "C", "cik": 3, "lei": "", "sector_de": "Handel", "fiscal_year": 2023},
        ],
    )
    out = tmp_path / "wb.twbx"
    monkeypatch.setattr(sys, "argv", ["build_workbook.py", "--csv", str(path), "--out", str(out)])
    bw.main()
    with zipfile.ZipFile(out) as zf:
        assert {"Data/wc_opportunity/wc_opportunity.csv", bw.HYPER_PATH} <= set(zf.namelist())
        root = ET.fromstring(zf.read("Bilanzwerk_Working_Capital.twb"))
        zf.extract(bw.HYPER_PATH, tmp_path)
    sheets = {w.get("name") for w in root.iter("worksheet")}
    assert sheets == set(bw.SHEETS)
    zones = {z.get("name") for z in root.iter("zone") if z.get("name")}
    assert sheets <= zones  # every sheet sits on the dashboard
    title = next(z for z in root.iter("zone") if z.get("id") == "2")
    assert "Energie hat den größten Hebel" in "".join(title.itertext())

    from tableauhyperapi import Connection, HyperProcess, Telemetry

    with (
        HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_config": ""}) as hyper,
        Connection(hyper.endpoint, str(tmp_path / bw.HYPER_PATH)) as conn,
    ):
        rows = conn.execute_list_query('SELECT "company_name", "cik", "lei" FROM "Extract"."Extract" ORDER BY "cik"')
    assert rows == [["B", 2, "1"], ["C", 3, None]]  # typed as in COLUMNS, empty cells are NULL


def test_check_against_h4_rejects_a_different_total():
    from tableau.build_workbook import check_against_h4

    h4 = {"top_sector": "Handel", "total_eur_bn": 10.0}
    check_against_h4({"top_sector": "Handel", "total_eur_bn": 10.2}, h4)
    with pytest.raises(SystemExit):
        check_against_h4({"top_sector": "Handel", "total_eur_bn": 13.0}, h4)
