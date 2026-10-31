"""The Tableau package must hold well-formed XML and a title computed from the packaged data."""

from __future__ import annotations

import csv
import importlib.util
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

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


def test_package_holds_parseable_workbook_and_the_data(tmp_path, monkeypatch):
    bw = load()
    path = tmp_path / "wc.csv"
    write_extract(path, [{"company_name": "B", "cik": 2, "sector_de": "Energie", "fiscal_year": 2024}])
    out = tmp_path / "wb.twbx"
    monkeypatch.setattr(sys, "argv", ["build_workbook.py", "--csv", str(path), "--out", str(out)])
    bw.main()
    with zipfile.ZipFile(out) as zf:
        assert "Data/wc_opportunity/wc_opportunity.csv" in zf.namelist()
        root = ET.fromstring(zf.read("Bilanzwerk_Working_Capital.twb"))
    sheets = {w.get("name") for w in root.iter("worksheet")}
    assert sheets == {"Brücke nach Sektor", "Top 20 Unternehmen", "Wo das Cash liegt", "KPI-Zeile"}
    zones = {z.get("name") for z in root.iter("zone") if z.get("name")}
    assert sheets <= zones  # every sheet sits on the dashboard
    title = next(z for z in root.iter("zone") if z.get("id") == "2")
    assert "Energie hat den größten Hebel" in "".join(title.itertext())
