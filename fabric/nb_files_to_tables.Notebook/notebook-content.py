# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# PARAMETERS CELL ********************

source = "ecb"  # sec_fsds | sec_submissions | esef | gleif | ecb | analysis | mdm
quarter = ""  # sec_fsds: replace only this quarter's partition
wheel_dir = "wheels/latest"  # holds exactly one wheel, replaced at every publish

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

# Each landed folder raw/<source>/<table>/<partitions>/*.parquet becomes the Delta table
# <source>_<table> that dbt reads across databases (dbt/models/staging/_sources.yml). The MDM
# and model outputs are single files: mdm/company_matches.parquet, analysis/risk_scores.parquet.
written_back = source in ("analysis", "mdm")
base = f"{abfss}/Files/bilanzwerk/" + (source if written_back else f"raw/{source}")
written = {}
for entry in notebookutils.fs.ls(base):
    if written_back:
        if entry.isDir or not entry.name.endswith(".parquet"):
            continue
        table = entry.name.removesuffix(".parquet")
        df = spark.read.parquet(f"{base}/{entry.name}")
    else:
        if not entry.isDir:
            continue
        table = entry.name.rstrip("/")
        path = f"{base}/{table}"
        df = spark.read.option("basePath", path).option("mergeSchema", "true").parquet(path)
    name = f"{source}_{table}"
    if source == "sec_fsds" and quarter:
        # The FSDS tables are large: replace one quarter, leave the others untouched.
        df = df.where(df.quarter == quarter)
        (
            df.write.format("delta")
            .mode("overwrite")
            .partitionBy("quarter")
            .option("replaceWhere", f"quarter = '{quarter}'")
            .saveAsTable(name)
        )
    else:
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
    written[name] = df.count()

notebookutils.notebook.exit(json.dumps(written))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
