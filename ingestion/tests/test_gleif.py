from __future__ import annotations

import pyarrow as pa
import pyarrow.dataset as ds

from ingestion import gleif
from ingestion.common.manifest import Manifest
from ingestion.tests.conftest import make_gleif_zip


def test_scrub_address_removes_person_fragments():
    arr = pa.array(["c/o Jane Doe, One Apple Park Way", "Attn: John Smith, Main St 1", "Hauptstr. 5", "c/o Max"])
    assert gleif.scrub_address(arr).to_pylist() == ["One Apple Park Way", "Main St 1", "Hauptstr. 5", None]


def test_land_keeps_allowlist_only_and_is_idempotent(settings, tmp_path):
    z = make_gleif_zip(tmp_path / "lei2.csv.zip")
    manifest = Manifest(settings.manifest_path)
    assert gleif.land_file(z, "lei2", "full", "2024-11-01", settings, manifest) == 1
    assert gleif.land_file(z, "lei2", "full", "2024-11-01", settings, manifest) == 0
    tbl = ds.dataset(settings.raw_root / "gleif" / "entities", format="parquet", partitioning="hive").to_table()
    row = tbl.to_pylist()[0]
    assert row["lei"] == "HWUPKR0MPOU8FGXBT394"
    assert row["legal_address_line"] == "One Apple Park Way"
    assert row["other_name_1"] == "AAPL"
    # privacy: mail routing never lands, and nothing in the table mentions the contact person
    assert not any("mail" in c.lower() for c in tbl.column_names)
    assert "Jane Doe" not in str(tbl.to_pylist())
    # missing optional columns (other_name_2..5, legal_form, ...) are present as nulls
    assert row["other_name_5"] is None and "legal_form_code" in tbl.column_names


def test_delta_window_covers_the_gap_since_the_last_load():
    from datetime import date

    from ingestion.gleif import choose_variant

    pub = date(2026, 10, 27)
    assert choose_variant(None, pub) == "full"
    assert choose_variant(date(2026, 10, 26), pub) == "LastDay"
    assert choose_variant(date(2026, 10, 22), pub) == "LastWeek"  # capacity paused for five days
    assert choose_variant(date(2026, 10, 1), pub) == "LastMonth"
    assert choose_variant(date(2026, 8, 1), pub) == "full"
    assert choose_variant(date(2026, 10, 26), pub, full=True) == "full"
