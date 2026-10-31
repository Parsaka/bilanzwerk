from __future__ import annotations

from datetime import date

import pyarrow.dataset as ds

from ingestion import sec_submissions
from ingestion.common.manifest import Manifest
from ingestion.tests.conftest import make_submissions_zip


def _table(settings, name):
    return ds.dataset(settings.raw_root / "sec_submissions" / name, format="parquet", partitioning="hive").to_table()


def test_keep_form():
    assert sec_submissions.keep_form("8-K")
    assert sec_submissions.keep_form("8-K/A")
    assert sec_submissions.keep_form("15-12G")
    assert sec_submissions.keep_form("25-NSE")
    assert sec_submissions.keep_form("NT 10-K")
    assert not sec_submissions.keep_form("SC 13G")
    assert not sec_submissions.keep_form("424B2")
    assert not sec_submissions.keep_form(None)


def test_land_flattens_recent_and_overflow_pages(settings, tmp_path):
    z = make_submissions_zip(tmp_path / "submissions.zip")
    manifest = Manifest(settings.manifest_path)
    counts = sec_submissions.land_zip(z, date(2024, 11, 1), settings, manifest)
    assert counts == {"companies": 1, "former_names": 1, "filings": 3}
    filings = _table(settings, "filings").to_pylist()
    by_acc = {f["accession_number"]: f for f in filings}
    assert by_acc["0000012345-24-000009"]["items"] == "1.03,9.01"
    assert by_acc["0000012345-10-000001"]["form"] == "10-K"  # from the overflow page
    assert "0000012345-24-000008" not in by_acc  # SC 13G filtered
    company = _table(settings, "companies").to_pylist()[0]
    assert company["sic"] == 5812 and company["tickers"] == ["TINY"]
    assert sec_submissions.land_zip(z, date(2024, 11, 1), settings, manifest) == {}
