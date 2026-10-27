"""Incident drill (spec, "CI/CD and operations"): an SEC quarter file arrives with a renamed column.

  uv run python scripts/incident_drill.py --fixture .ci-data --out docs/incident-drill.md

Runs on a copy of the CI fixture (synthetic companies, real loaders and dbt project):
1. A re-published quarter zip whose num.txt calls the column "value" "amount".
2. Detection: the loader's column contract stops the load; the manifest records the failure;
   no partition of that quarter changes; the marts still show the last good load.
3. Fix: the rename is triaged as a pure rename and mapped (sec_fsds.COLUMN_ALIASES).
4. Rerun of only that quarter: loader for the one zip, dbt build with load_quarter.
5. Check: the marts are identical to before the incident.

Writes the timings and the observed outputs to the report; nothing in it is typed by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from ingestion import sec_fsds
from ingestion.common.config import Settings
from ingestion.common.manifest import Manifest

ROOT = Path(__file__).resolve().parents[1]
QUARTER = "2022q3"
CHECK_SQL = {
    "fact_financial_line rows": "select count(*) from marts.fact_financial_line",
    # Rounded per row and summed as decimal: exact, independent of the parallel summation order.
    "sum of amount_local": "select sum(cast(round(amount_local, 2) as decimal(38, 2))) from marts.fact_financial_line",
    "fact_kpi rows": "select count(*) from marts.fact_kpi",
}


def partition_digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted((root / "raw" / "sec_fsds").rglob(f"quarter={QUARTER}/*.parquet")):
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


def marts(db: Path) -> dict[str, object]:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return {k: con.execute(q).fetchone()[0] for k, q in CHECK_SQL.items()}
    finally:
        con.close()


def renamed_zip(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.lower() == "num.txt":
                header, rest = data.split(b"\n", 1)
                cols = header.decode().split("\t")
                cols[cols.index("value")] = "amount"
                data = "\t".join(cols).encode() + b"\n" + rest
            zout.writestr(item, data)


def dbt(args: list[str], env: dict[str, str]) -> tuple[int, str]:
    result = subprocess.run(
        ["dbt", *args, "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt")],
        env=env,
        capture_output=True,
        text=True,
        check=False,  # the exit code is part of the report
    )
    done = [ln for ln in result.stdout.splitlines() if "Done." in ln]
    return result.returncode, done[-1].split("Done.", 1)[1].strip() if done else result.stdout[-500:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--fixture", default=".ci-data", type=Path)
    parser.add_argument("--out", default=ROOT / "docs" / "incident-drill.md", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "drill"
        shutil.copytree(args.fixture, root, ignore=shutil.ignore_patterns("mlruns"))
        settings = Settings(data_root=root, user_agent="drill drill@example.com", min_seconds_between_requests=0)
        manifest = Manifest(settings.manifest_path)
        env = dict(os.environ, BW_DATA_ROOT=str(root), BW_HAS_MDM="true", BW_HAS_RISK_SCORES="true")
        db = root / "bilanzwerk.duckdb"
        before_marts = marts(db)
        before_part = partition_digest(root)

        bad = root / "src" / f"{QUARTER}_republished.zip"
        renamed_zip(root / "src" / f"{QUARTER}.zip", bad)

        t0 = time.perf_counter()
        try:
            sec_fsds.land_zip(bad, sec_fsds.Quarter.parse(QUARTER), settings, manifest)
            raise SystemExit("drill failed: the contract did not catch the renamed column")
        except sec_fsds.ContractError as exc:
            detect_s = time.perf_counter() - t0
            error = str(exc)
        failed = [r for r in manifest.rows("sec_fsds") if r[1] == bad.name]
        after_fail_part = partition_digest(root)
        code, dbt_after_fail = dbt(["build", "--vars", "{wc_min_sector_peers: 1}"], env)
        after_fail_marts = marts(db)

        # Fix: triaged as a pure rename -> one alias entry (in the repo: a commit with a test).
        sec_fsds.COLUMN_ALIASES["num"]["amount"] = "value"
        t1 = time.perf_counter()
        counts = sec_fsds.land_zip(bad, sec_fsds.Quarter.parse(QUARTER), settings, manifest)
        load_s = time.perf_counter() - t1
        t2 = time.perf_counter()
        code2, dbt_rerun = dbt(["build", "--vars", f"{{wc_min_sector_peers: 1, load_quarter: {QUARTER}}}"], env)
        dbt_s = time.perf_counter() - t2
        after_fix_marts = marts(db)

    ok = after_fail_part == before_part and after_fail_marts == before_marts == after_fix_marts and code2 == 0
    buf = io.StringIO()
    w = buf.write
    w("# Incident drill: renamed column in an SEC quarter file\n\n")
    w(f"Generated by `scripts/incident_drill.py` on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC against the CI fixture ")
    w("(synthetic companies, the real loaders and dbt project). Rerun it after changes to the loader or the ")
    w("staging models; the numbers below come from that run, not from hand.\n\n")
    w(f"**Result: {'passed' if ok else 'FAILED'}.**\n\n")
    w("## Scenario\n\n")
    w(f"The SEC re-publishes `{QUARTER}.zip`; in `num.txt` the column `value` is now called `amount`. ")
    w("Without a contract the loader would land a quarter without amounts and every KPI of that quarter ")
    w("would silently be empty.\n\n")
    w("## Timeline\n\n| Step | Observed |\n|---|---|\n")
    w(f"| 1. Load the new file | stopped after {detect_s:.2f} s: `{error}` |\n")
    w(f"| 2. Manifest | {len(failed)} row with status `{failed[0][9] if failed else '-'}` for `{bad.name}` |\n")
    unchanged = before_part == after_fail_part
    w(f"| 3. Landed partitions of {QUARTER} | unchanged: {unchanged} (digest {after_fail_part}) |\n")
    w(f"| 4. dbt build after the failed load | exit {code}: {dbt_after_fail} |\n")
    w(f"| 5. Marts after the failed load | unchanged: {after_fail_marts == before_marts} |\n")
    w("| 6. Fix | rename triaged as pure rename; `COLUMN_ALIASES['num'] = {'amount': 'value'}` plus a test |\n")
    w(f"| 7. Rerun the loader for {QUARTER} only | {load_s:.2f} s, rows {counts} |\n")
    w(f"| 8. `dbt build --vars '{{load_quarter: {QUARTER}}}'` | {dbt_s:.1f} s, {dbt_rerun} |\n")
    w(f"| 9. Marts after the rerun | identical to before the incident: {after_fix_marts == before_marts} |\n\n")
    w("## Mart checks\n\n| Check | Before | After failed load | After rerun |\n|---|---:|---:|---:|\n")
    for k in CHECK_SQL:
        w(f"| {k} | {before_marts[k]} | {after_fail_marts[k]} | {after_fix_marts[k]} |\n")
    w("\n## What made it work\n\n")
    w("- The column contract (`REQUIRED` in `ingestion/sec_fsds.py`) is checked for every table of the zip ")
    w("before any partition is written, so a broken file cannot leave a half-replaced quarter.\n")
    w("- The manifest records the failed file with its checksum; the file is not marked as loaded, so the ")
    w("next run retries it.\n")
    w("- Satellites are insert-only and incremental, so the rerun of one quarter adds nothing when the ")
    w("content is unchanged; the marts come out identical.\n")
    w("- In production the failed `pl_load_sec_fsds` sends the failure e-mail; the reports keep showing ")
    w("the last good load because `pl_transform` does not run after a failed load.\n")
    args.out.write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue())
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
