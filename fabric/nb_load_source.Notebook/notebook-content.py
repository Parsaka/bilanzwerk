# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# PARAMETERS CELL ********************

source = "ecb"              # sec_fsds | sec_submissions | esef | gleif | ecb
quarter = ""                # sec_fsds only, e.g. 2026q3; empty: every quarter not yet loaded
gleif_full = False          # gleif only: force the full golden copy
key_vault_uri = ""          # set by the pipeline (parameter KeyVaultUri)
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

# The declared SEC User-Agent comes from Key Vault, never from Git.
os.environ["BW_USER_AGENT"] = notebookutils.credentials.getSecret(key_vault_uri, "sec-user-agent")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

%pip install -q {wheel_path}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from ingestion.cli import app
from ingestion.common.config import get_settings
from ingestion.common.manifest import Manifest

args = {
    "sec_fsds": ["sec-fsds"] + (["--start", quarter, "--end", quarter] if quarter else []),
    "sec_submissions": ["sec-submissions"],
    "esef": ["esef"],
    "gleif": ["gleif"] + (["--full"] if gleif_full else []),
    "ecb": ["ecb"],
}[source]
app(args, standalone_mode=False)

# Exit value for the pipeline log: the manifest rows of this source (newest 20).
rows = Manifest(get_settings().manifest_path).rows(source)[-20:]
notebookutils.notebook.exit(json.dumps([{"file": r[1], "rows": r[6], "status": r[9]} for r in rows], default=str))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
