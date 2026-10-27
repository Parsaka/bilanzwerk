# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# PARAMETERS CELL ********************

semantic_model = "Bilanzwerk"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Direct Lake: a refresh reframes the model on the new Delta versions of the warehouse tables.
# Found by name in the workspace this notebook runs in, so dev and prod need no IDs.
import json
import time

import notebookutils
from sempy import fabric

request_id = fabric.refresh_dataset(semantic_model, refresh_type="full")
status = fabric.get_refresh_execution_details(semantic_model, request_id)
while status.status in ("Unknown", "NotStarted", "InProgress"):
    time.sleep(15)
    status = fabric.get_refresh_execution_details(semantic_model, request_id)
if status.status != "Completed":
    raise RuntimeError(f"semantic model refresh ended with {status.status}: {status.messages}")
notebookutils.notebook.exit(json.dumps({"refresh": status.status, "request_id": str(request_id)}))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
