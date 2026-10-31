"""Writing landed data as Parquet, with Hive-style partition folders."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def write_partition(table: pa.Table, root: Path, partition: dict[str, str], name: str = "part-0") -> Path:
    """Write one table into root/<k=v>/.../<name>.parquet, replacing the file if it exists.

    Replacing (not appending) is what makes a rerun of the same input idempotent.
    """
    folder = root
    for key, value in partition.items():
        folder = folder / f"{key}={value}"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{name}.parquet"
    tmp = target.with_suffix(".parquet.part")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(target)
    return target
