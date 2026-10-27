"""Run Fabric pipelines by name, wait for them, and write a job summary.

  uv run --extra deploy python scripts/fabric_run.py run --workspace-id <id> pl_load_gleif pl_load_ecb pl_transform
  uv run --extra deploy python scripts/fabric_run.py run --workspace-id <id> pl_master --param Quarter=2026q3
  uv run --extra deploy python scripts/fabric_run.py summary --workspace-id <id>
  uv run --extra deploy python scripts/fabric_run.py latest-quarter --workspace-id <id>

Used by the scheduled GitHub workflows, which resume the capacity before and pause it after
(scripts/fabric_capacity.sh). Pipelines given together run one after the other; the command
fails on the first pipeline that does not complete.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time

import requests

API = "https://api.fabric.microsoft.com/v1"
POLL_SECONDS = 30
TIMEOUT_SECONDS = 6 * 3600


def credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def headers(cred) -> dict[str, str]:
    token = cred.get_token("https://api.fabric.microsoft.com/.default").token
    return {"Authorization": f"Bearer {token}"}


def item_id(cred, workspace_id: str, name: str, kind: str = "DataPipeline") -> str:
    resp = requests.get(
        f"{API}/workspaces/{workspace_id}/items", params={"type": kind}, headers=headers(cred), timeout=60
    )
    resp.raise_for_status()
    for item in resp.json()["value"]:
        if item["displayName"] == name:
            return item["id"]
    raise SystemExit(f"{kind} {name} not found in workspace {workspace_id}")


def run_pipeline(cred, workspace_id: str, name: str, params: dict[str, str]) -> str:
    pid = item_id(cred, workspace_id, name)
    body = {"executionData": {"parameters": params}} if params else None
    resp = requests.post(
        f"{API}/workspaces/{workspace_id}/items/{pid}/jobs/instances",
        params={"jobType": "Pipeline"},
        json=body,
        headers=headers(cred),
        timeout=60,
    )
    resp.raise_for_status()
    location = resp.headers["Location"]
    started = time.monotonic()
    while True:
        time.sleep(POLL_SECONDS)
        status = requests.get(location, headers=headers(cred), timeout=60)
        status.raise_for_status()
        job = status.json()
        state = job.get("status")
        print(f"{name}: {state}", flush=True)
        if state in ("Completed", "Failed", "Cancelled", "Deduped"):
            if state != "Completed":
                reason = (job.get("failureReason") or {}).get("message", "")
                raise SystemExit(f"{name} ended with {state}: {reason}")
            return state
        if time.monotonic() - started > TIMEOUT_SECONDS:
            raise SystemExit(f"{name} still running after {TIMEOUT_SECONDS // 3600} h")


def sql_connection(cred, workspace_id: str):
    import pyodbc

    resp = requests.get(f"{API}/workspaces/{workspace_id}/warehouses", headers=headers(cred), timeout=60)
    resp.raise_for_status()
    wh = next(w for w in resp.json()["value"] if w["displayName"] == "wh_bilanzwerk")
    token = cred.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
    attrs = {1256: struct.pack(f"<I{len(token)}s", len(token), token)}  # SQL_COPT_SS_ACCESS_TOKEN
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={wh['properties']['connectionString']},1433;Database=wh_bilanzwerk;Encrypt=yes"
    )
    return pyodbc.connect(conn_str, attrs_before=attrs)


SUMMARY_SQL = {
    "rows": """
        select 'fact_financial_line', count_big(*) from marts.fact_financial_line union all
        select 'fact_kpi', count_big(*) from marts.fact_kpi union all
        select 'fact_event', count_big(*) from marts.fact_event union all
        select 'fact_risk_score', count_big(*) from marts.fact_risk_score union all
        select 'dim_company (current)', count_big(*) from marts.dim_company where is_current = 1
    """,
    "dq": """
        select rule_code, dq_dimension, rows_checked, rows_failed, pass_rate, target_pass_rate, status
        from marts.fact_data_quality
        where run_at = (select max(run_at) from marts.fact_data_quality)
        order by case status when 'fail' then 0 else 1 end, rule_code
    """,
    "latest_quarter": "select max(quarter) from lh_bilanzwerk.dbo.sec_fsds_sub",
}


def summary(cred, workspace_id: str) -> str:
    with sql_connection(cred, workspace_id) as con:
        rows = con.execute(SUMMARY_SQL["rows"]).fetchall()
        dq = con.execute(SUMMARY_SQL["dq"]).fetchall()
        quarter = con.execute(SUMMARY_SQL["latest_quarter"]).fetchone()[0]
    lines = [f"### Bilanzwerk load: latest SEC quarter {quarter}", "", "| Table | Rows |", "|---|---:|"]
    lines += [f"| {t} | {n:,} |" for t, n in rows]
    lines += [
        "",
        "| Rule | Dimension | Checked | Failed | Pass rate | Target | Status |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for code, dim, checked, failed, rate, target, status in dq:
        rate_s = "" if rate is None else f"{rate:.1%}"
        target_s = "" if target is None else f"{target:.0%}"
        lines.append(f"| {code} | {dim} | {checked:,} | {failed:,} | {rate_s} | {target_s} | {status} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("pipelines", nargs="+")
    p_run.add_argument("--param", action="append", default=[], help="Name=value, passed to every pipeline given")
    for p in (p_run, sub.add_parser("summary"), sub.add_parser("latest-quarter")):
        p.add_argument("--workspace-id", required=True)
    args = parser.parse_args()
    cred = credential()

    if args.cmd == "run":
        params = dict(kv.split("=", 1) for kv in args.param)
        for name in args.pipelines:
            run_pipeline(cred, args.workspace_id, name, params)
    elif args.cmd == "summary":
        text = summary(cred, args.workspace_id)
        print(text)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(text)
    else:
        with sql_connection(cred, args.workspace_id) as con:
            print(con.execute(SUMMARY_SQL["latest_quarter"]).fetchone()[0] or "")


if __name__ == "__main__":
    sys.exit(main())
