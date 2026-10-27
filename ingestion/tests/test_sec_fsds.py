from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.dataset as ds
import pytest

from ingestion import sec_fsds
from ingestion.common.manifest import Manifest
from ingestion.tests.conftest import NUM, SUB, make_fsds_zip

Q = sec_fsds.Quarter(2024, 3)


def _rows(settings, table):
    return ds.dataset(settings.raw_root / "sec_fsds" / table, format="parquet", partitioning="hive").to_table()


def test_list_quarters_starts_2009q2_and_stops_at_last_completed():
    qs = sec_fsds.list_quarters(today=date(2026, 10, 27))
    assert qs[0].label == "2009q2"
    assert qs[-1].label == "2026q3"
    assert len(qs) == 70  # "about 70 downloads in total"


def test_list_quarters_in_first_quarter_ends_previous_year():
    assert sec_fsds.list_quarters(sec_fsds.Quarter(2025, 3), today=date(2026, 2, 1))[-1].label == "2025q4"


def test_column_types_are_enforced(settings, fsds_zip):
    sec_fsds.land_zip(fsds_zip, Q, settings, Manifest(settings.manifest_path))
    num = _rows(settings, "num")
    assert num.schema.field("adsh").type == pa.string()
    assert num.schema.field("value").type == pa.decimal128(38, 6)
    assert num.schema.field("ddate").type == pa.date32()
    assert num.schema.field("qtrs").type == pa.int32()
    assert Decimal("1234.56") in num.column("value").to_pylist()
    sub = _rows(settings, "sub")
    assert sub.schema.field("cik").type == pa.int64()
    assert pa.types.is_timestamp(sub.schema.field("accepted").type)
    assert sub.column("filed").to_pylist()[0] == date(2024, 11, 1)


def test_checksum_skip_works(settings, fsds_zip):
    manifest = Manifest(settings.manifest_path)
    first = sec_fsds.land_zip(fsds_zip, Q, settings, manifest)
    second = sec_fsds.land_zip(fsds_zip, Q, settings, manifest)
    assert first == {"sub": 2, "num": 5, "tag": 2, "pre": 2}
    assert second == {}
    assert len(manifest.rows("sec_fsds")) == 4  # one per table, not eight


def test_same_quarter_gives_same_row_count_twice(settings, tmp_path):
    """A re-published zip (new checksum, same content) replaces the partition, never appends."""
    a = make_fsds_zip(tmp_path / "a.zip")
    b = make_fsds_zip(tmp_path / "b.zip", num=NUM + "")
    with zipfile.ZipFile(b, "a") as zf:  # change the checksum without changing the data
        zf.writestr("extra.txt", "x")
    manifest = Manifest(settings.manifest_path)
    sec_fsds.land_zip(a, Q, settings, manifest)
    n1 = _rows(settings, "num").num_rows
    sec_fsds.land_zip(b, Q, settings, manifest)
    assert _rows(settings, "num").num_rows == n1 == 5


def test_broken_zip_fails_loudly(settings, tmp_path):
    broken = tmp_path / "2024q3.zip"
    broken.write_bytes(b"PK\x03\x04 this is not really a zip")
    manifest = Manifest(settings.manifest_path)
    with pytest.raises(zipfile.BadZipFile):
        sec_fsds.land_zip(broken, Q, settings, manifest)
    rows = manifest.rows("sec_fsds")
    assert rows and rows[0][9] == "failed"
    assert not manifest.is_loaded("sec_fsds", rows[0][4])


def test_renamed_column_is_caught_by_contract(settings, tmp_path):
    """Incident drill: the SEC renames a column -> the load fails before anything lands."""
    renamed = make_fsds_zip(tmp_path / "x.zip", num=NUM.replace("\tddate\t", "\tdate_end\t", 1))
    with pytest.raises(sec_fsds.ContractError, match="ddate"):
        sec_fsds.land_zip(renamed, Q, settings, Manifest(settings.manifest_path))


def test_missing_optional_column_is_added_as_null(settings, tmp_path):
    old_style = NUM.replace("\tsegments", "", 1).replace("\t\t\t", "\t\t", 3)
    lines = [ln.split("\t") for ln in old_style.strip().split("\n")]
    assert all(len(ln) == len(lines[0]) for ln in lines[:4])
    z = make_fsds_zip(tmp_path / "old.zip", num="\n".join("\t".join(ln) for ln in lines[:4]) + "\n")
    sec_fsds.land_zip(z, Q, settings, Manifest(settings.manifest_path))
    num = _rows(settings, "num")
    assert "segments" in num.column_names
    assert num.column("segments").null_count == num.num_rows


def test_newly_published_stops_at_the_first_missing_quarter():
    from datetime import date

    from ingestion.sec_fsds import Quarter, newly_published

    published = ("2026q1", "2026q2")

    class FakeSession:
        def head(self, url):
            class R:
                status_code = 200 if any(q in url for q in published) else 404

            return R()

    today = date(2026, 10, 27)  # last completed quarter: 2026q3, not yet published
    assert [q.label for q in newly_published(Quarter(2025, 4), FakeSession(), today=today)] == ["2026q1", "2026q2"]
    assert newly_published(Quarter(2026, 2), FakeSession(), today=today) == []


def test_contract_break_leaves_the_landed_quarter_untouched(settings, tmp_path):
    """sub.txt is fine (and changed), num.txt breaks the contract: no table of the quarter changes."""
    manifest = Manifest(settings.manifest_path)
    sec_fsds.land_zip(make_fsds_zip(tmp_path / "good.zip"), Q, settings, manifest)
    names_before = _rows(settings, "sub").column("name").to_pylist()
    bad = make_fsds_zip(
        tmp_path / "bad.zip",
        num=NUM.replace("\tddate\t", "\tdate_end\t", 1),
        sub=SUB.replace("APPLE INC", "APPLE INC RENAMED"),
    )
    with pytest.raises(sec_fsds.ContractError):
        sec_fsds.land_zip(bad, Q, settings, manifest)
    assert _rows(settings, "sub").column("name").to_pylist() == names_before
    assert "APPLE INC RENAMED" not in names_before
    assert _rows(settings, "num").num_rows == 5


def test_column_alias_maps_a_triaged_rename(settings, tmp_path, monkeypatch):
    monkeypatch.setitem(sec_fsds.COLUMN_ALIASES, "num", {"date_end": "ddate"})
    renamed = make_fsds_zip(tmp_path / "x.zip", num=NUM.replace("\tddate\t", "\tdate_end\t", 1))
    sec_fsds.land_zip(renamed, Q, settings, Manifest(settings.manifest_path))
    num = _rows(settings, "num")
    assert "ddate" in num.column_names and "date_end" not in num.column_names
    assert num.column("ddate").null_count == 0
