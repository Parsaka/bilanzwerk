# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# PARAMETERS CELL ********************

dbt_target = "dev"          # dev | prod; the master pipeline passes its Stage parameter
dbt_select = ""             # empty: whole project
full_refresh = False
wheel_dir = "wheels/latest"      # holds exactly one wheel, replaced at every publish

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Mount the project lakehouse by name: no workspace-specific IDs, so the deployment pipeline
# promotes this notebook to prod unchanged.
import json
import os
from pathlib import Path

import notebookutils

lakehouse = notebookutils.lakehouse.getWithProperties("lh_bilanzwerk")
abfss = lakehouse["properties"]["abfsPath"]
if not any(m.mountPoint == "/bilanzwerk" for m in notebookutils.fs.mounts()):
    notebookutils.fs.mount(abfss, "/bilanzwerk")
files = notebookutils.fs.getMountPath("/bilanzwerk") + "/Files"
os.environ["BW_DATA_ROOT"] = f"{files}/bilanzwerk"
wheel_path = sorted(Path(f"{files}/{wheel_dir}").glob("*.whl"))[-1]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

%pip install -q "dbt-fabric>=1.9,<1.10"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import subprocess
import tempfile

import requests

# SQL endpoint of the warehouse in the workspace this notebook runs in (dev or prod), so the
# same notebook works in every stage without stage-specific parameters.
workspace_id = notebookutils.runtime.context["currentWorkspaceId"]
token = notebookutils.credentials.getToken("pbi")
resp = requests.get(
    f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/warehouses",
    headers={"Authorization": f"Bearer {token}"},
    timeout=60,
)
resp.raise_for_status()
warehouse = next(w for w in resp.json()["value"] if w["displayName"] == "wh_bilanzwerk")
sql_endpoint = warehouse["properties"]["connectionString"]

# The dbt project is published next to the wheel by .github/workflows/dbt-build.yml.
project = tempfile.mkdtemp()
subprocess.run(["unzip", "-q", f"{files}/dbt/bilanzwerk-dbt.zip", "-d", project], check=True)

env = dict(
    os.environ,
    BW_DBT_TARGET=dbt_target,
    BW_FABRIC_SQL_ENDPOINT=sql_endpoint,
    BW_FABRIC_SQL_ENDPOINT_PROD=sql_endpoint,
    BW_FABRIC_AUTH="fabricnotebook",   # token of the identity running the notebook
    BW_HAS_MDM="true",
    BW_HAS_RISK_SCORES="true",
    DBT_PROFILES_DIR=project,
)
cmd = ["dbt", "build", "--project-dir", project]
if dbt_select:
    cmd += ["--select", dbt_select]
if full_refresh:
    cmd.append("--full-refresh")
result = subprocess.run(cmd, env=env, capture_output=True, text=True)
print(result.stdout[-20000:])
if result.returncode != 0:
    print(result.stderr[-5000:])
    raise RuntimeError("dbt build failed: see the log above")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Balance-check pass rate of this run (SLA >= 98 %) and failed rules, for the pipeline's
# alert condition and the job summary.
import com.microsoft.spark.fabric  # noqa: F401  (registers spark.read.synapsesql)

dq = spark.read.synapsesql("wh_bilanzwerk.marts.fact_data_quality")
latest = dq.agg({"run_at": "max"}).first()[0]
run = dq.where(dq.run_at == latest)
balance = run.where(run.rule_code == "CONS_BALANCE_CHECK").first()
failed = run.where(run.status == "fail").count()
notebookutils.notebook.exit(json.dumps({
    "dq_pass_rate": float(balance["pass_rate"]) if balance and balance["pass_rate"] is not None else 0.0,
    "rules_failed": failed,
}))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
