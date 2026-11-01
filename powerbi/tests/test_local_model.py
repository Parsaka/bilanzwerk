"""The local import-mode model: same tables and measures, Parquet partitions, report bound to it."""

import json
import subprocess
import sys
from pathlib import Path

PBI = Path(__file__).resolve().parents[1]


def test_local_model_reads_parquet_and_keeps_the_measures():
    subprocess.run([sys.executable, str(PBI / "tools" / "generate_tmdl.py"), "--local"], check=True)
    local = PBI / "local"
    tables = local / "Bilanzwerk.Local.SemanticModel" / "definition" / "tables"
    kpi = (tables / "fact_kpi.tmdl").read_text()
    assert "mode: import" in kpi and 'MartsFolder & "\\fact_kpi.parquet"' in kpi
    assert "directLake" not in "".join(p.read_text() for p in tables.glob("*.tmdl"))
    original = PBI / "Bilanzwerk.SemanticModel" / "definition" / "tables"
    assert sorted(p.name for p in tables.glob("*.tmdl")) == sorted(p.name for p in original.glob("*.tmdl"))
    count = sum(p.read_text().count("\tmeasure ") for p in tables.glob("*.tmdl"))
    assert count == sum(p.read_text().count("\tmeasure ") for p in original.glob("*.tmdl"))
    pbir = json.loads((local / "Bilanzwerk.Local.Report" / "definition.pbir").read_text())
    assert pbir["datasetReference"]["byPath"]["path"] == "../Bilanzwerk.Local.SemanticModel"
