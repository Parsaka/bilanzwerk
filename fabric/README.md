# Fabric items (Data Factory pipelines and notebooks)

Folders in the Fabric Git format (`<name>.<ItemType>/` with a `.platform` file). They are
published to the dev and prod workspaces by `scripts/fabric_publish.py` (fabric-cicd), together
with the semantic model and report from `powerbi/`. Item references use logical IDs and the
zero workspace GUID; fabric-cicd rewrites them to the IDs in the target workspace, so Git holds
no workspace-specific IDs (ADR-009, amendment).

| Item | What it does |
|---|---|
| `nb_load_source` | Installs the project wheel from `Files/wheels/latest` and runs one loader (`bilanzwerk sec-fsds`, `gleif`, ...) with the SEC User-Agent from Key Vault. Exit value: the newest manifest rows. |
| `nb_files_to_tables` | Turns `Files/bilanzwerk/raw/<source>/<table>` into the Delta table `<source>_<table>` that dbt reads; for FSDS with a quarter it replaces only that partition. |
| `nb_dbt_build` | Finds the warehouse endpoint of its own workspace, runs `dbt build` (dbt-fabric, notebook identity), returns the balance-check pass rate and the number of failed rules. |
| `nb_refresh_model` | Refreshes (reframes) the Direct Lake semantic model by name with semantic link. |
| `pl_load_<source>` (5) | Load, then files to tables; an e-mail if either step fails. |
| `pl_transform` | MDM and model outputs to tables, dbt build, model refresh; e-mail when dbt or the refresh fails or the balance check is under 98 %. |
| `pl_master` | All five loads in parallel (FSDS for one quarter or every missing one), then `pl_transform`. |

## Schedules

The capacity is paused when nobody works (cost, ADR-009), and a paused capacity cannot run a
Fabric schedule. The schedules therefore live in GitHub Actions, which resume the capacity, run
the pipelines through the Fabric API (`scripts/fabric_run.py`), write a job summary and pause it
again:

| Spec cadence | Workflow | Pipelines |
|---|---|---|
| GLEIF and ECB daily | `daily-load.yml`, 05:30 UTC | `pl_load_gleif`, `pl_load_ecb`, `pl_transform` |
| Submissions weekly | `daily-load.yml`, Sundays | also `pl_load_sec_submissions`, `pl_load_esef` |
| FSDS quarterly | `quarterly-load.yml`, checks daily whether the next quarter is published; manual with a quarter | `pl_master` with `Quarter` |

Checking daily for the quarterly file is what makes the freshness target (new SEC quarter in the
reports within 24 hours) reachable. The loaders are incremental, so a missed day is caught up by
the next run (GLEIF picks a delta window that covers the gap).

## Where MDM and the early-warning model run

Splink matching (`mdm/`) and the model (`analysis/`) run on DuckDB over the same landed files
(locally or on a GitHub runner), quarterly after the FSDS load. Their outputs
(`Files/bilanzwerk/mdm/company_matches.parquet`, `Files/bilanzwerk/analysis/risk_scores.parquet`) are
uploaded to the lakehouse and picked up by `pl_transform`. This keeps the Python stack in one
place and matches ADR-003 (the same dbt project on DuckDB and Fabric).

## Alert e-mails

The Office 365 Outlook activities need a connection created once in the workspace (sign in as
the sending account). The recipient is the pipeline parameter `AlertEmail`, filled at publish
time.

## Not yet run against a workspace

These items were written against the Fabric Git item format and checked by fabric-cicd's
publish logic (reference rewriting), but have not been executed in a real workspace yet. Things
to verify on the first run: the `fabricnotebook` authentication of dbt-fabric inside the
notebook, the ODBC driver in the Spark runtime, and the Outlook connection binding.
