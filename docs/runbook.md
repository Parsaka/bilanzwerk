# Runbook

How to run, recover and rerun. Commands assume the repo root and `uv sync --all-extras`.

## Environment variables

| Variable | Meaning | Example |
|---|---|---|
| `BW_DATA_ROOT` | Landing zone and local warehouse folder | `./data` (local); in Fabric the notebooks set it to the mounted lakehouse `Files/bilanzwerk` |
| `BW_USER_AGENT` | Declared User-Agent for the SEC (name and e-mail) | `Parsa Kamali parsa@example.com` |
| `BW_DBT_TARGET` | `local` (DuckDB), `dev`, `prod` (Fabric) | `local` |
| `BW_FABRIC_SQL_ENDPOINT` | Warehouse SQL endpoint for dev | `xxxx.datawarehouse.fabric.microsoft.com` |
| `BW_LAKEHOUSE` | Lakehouse name for cross-database sources | `lh_bilanzwerk` |
| `BW_HAS_MDM` / `BW_HAS_RISK_SCORES` | Read the MDM / analysis write-back | `true` after the first run |

## Full run (first time)

```bash
export BW_DATA_ROOT=./data BW_USER_AGENT="Your Name you@example.com"
uv run bilanzwerk ecb                         # ~ 1 request
uv run bilanzwerk sec-fsds --start 2009q2     # ~ 70 zips, pauses between files
uv run bilanzwerk sec-submissions             # ~ 1.5 GB zip
uv run bilanzwerk gleif --full                # golden copy, then daily deltas without --full
uv run bilanzwerk esef --countries DE --countries FR --countries NL
cd dbt && uv run dbt seed && uv run dbt build && cd ..
uv run python -m mdm.cli match                # writes data/mdm/company_matches.parquet
cd dbt && BW_HAS_MDM=true uv run dbt build && cd ..
uv run bw-analysis events                     # event count check (week 5)
uv run bw-analysis run                        # backtest, statistics, write-back
cd dbt && BW_HAS_MDM=true BW_HAS_RISK_SCORES=true uv run dbt build && cd ..
```

A second run of any loader loads nothing new (checksum in `ingest_manifest`).

## Scheduled loads (prod)

| Workflow | When | What |
|---|---|---|
| `daily-load.yml` | 05:30 UTC daily | GLEIF and ECB (plus SEC submissions and ESEF on Sundays), then `pl_transform` |
| `quarterly-load.yml` | 07:00 UTC daily check | When `bilanzwerk sec-fsds-check` finds a newly published quarter: `pl_master` for it, job summary |
| `capacity-pause.yml` | 19:00 UTC daily | Pauses the capacity, whatever left it running |

Each run resumes the capacity, runs the pipelines through the Fabric API
(`scripts/fabric_run.py`), writes row counts and the data quality table to the job summary and
pauses the capacity again. The last loaded SEC quarter is kept in the landing storage account
(`archive/state/last_sec_quarter.txt`); after the first history load from a PC, write it once:
`echo 2026q3 > last.txt && az storage blob upload --auth-mode login --account-name <storage> -c archive -n state/last_sec_quarter.txt -f last.txt`.

## New SEC quarter

1. `quarterly-load.yml` finds the quarter (or is started by hand with `quarter=2026q4`) and runs
   `pl_master` with `Quarter=2026q4`.
2. The FSDS loader lands only that quarter; `nb_files_to_tables` replaces only its partition;
   vault models insert only new keys and changed attributes.
3. The job summary shows row counts and the data quality pass rate; a balance-check pass rate
   under 98 % sends the data quality e-mail.

## Deploy

Merge to `main` runs `dbt-build.yml`: publish to the dev workspace (`scripts/fabric_publish.py`),
dbt build against the dev warehouse, dbt docs to GitHub Pages; after approval of the `prod`
environment, the same publish to prod and `pl_transform` there. Infrastructure changes go
through `terraform.yml` (plan on the pull request, apply after approval).

## Rerun one quarter (incident drill)

Scenario: the SEC renames a column in one quarter file. The drill is scripted and was run on the
CI fixture: `uv run python scripts/incident_drill.py` (report: `docs/incident-drill.md`).

1. The loader's column contract stops the load before any table of the quarter is written:
   `ContractError: num.txt is missing required columns: [...]`; a `failed` row goes to the
   manifest; `pl_load_sec_fsds` sends the failure e-mail; `pl_transform` does not run, so the
   reports keep the last good load.
2. Triage: compare the new header with the contract. A pure rename (same meaning, same values)
   gets one entry in `COLUMN_ALIASES` in `ingestion/sec_fsds.py` plus a test with a fixture in the
   new layout; anything else is a new contract version with an ADR.
3. Rerun only that quarter: `quarterly-load.yml` with `quarter=2026q4` (or locally
   `uv run bilanzwerk sec-fsds --start 2026q4 --end 2026q4`, then
   `dbt build --vars '{load_quarter: 2026q4}'`).
4. Check the job summary against the previous run; add a line to `CHANGELOG.md`.

## Recover

| Problem | Action |
|---|---|
| SEC blocks downloads from the cloud | Run `bilanzwerk sec-fsds` once on a PC, upload `data/raw/sec_fsds` to the Lakehouse; the pipeline then fetches only new quarters. |
| A raw vault table must be rebuilt (history loaded out of order) | `dbt build --select raw_vault+ --full-refresh` |
| Broken zip / partial download | Delete the file in `downloads/`; the next run downloads again (the manifest only knows loaded checksums). |
| Fabric trial ended | Point `BW_DBT_TARGET=local` and use Power BI Import mode (fallback in ADR-003). |

## Service levels

| SLA | Target | Where it is measured |
|---|---|---|
| Freshness | New SEC quarter in the reports within 24 hours | `TIMELY_SEC_QUARTER` in `fact_data_quality`, dbt source freshness |
| Quality | >= 98 % of filings pass the balance check | `CONS_BALANCE_CHECK`, singular test `assert_balance_check_pass_rate` |
| Refresh | Semantic model refresh after load succeeds in 99 % of runs | Fabric pipeline run history |

Alerts: a failed pipeline activity or a data quality pass rate under target sends an e-mail
(Fabric pipeline "Office 365 Outlook" activities; see `fabric/README.md`). Azure budget alerts at
80 % actual and 100 % forecast go to the same address.

## Costs

Start on the Fabric trial; afterwards the smallest pay-as-you-go F capacity (F2), paused whenever
nobody works (`infra/terraform` creates it; `scripts/fabric_capacity.sh pause|resume|status`, and
`capacity-pause.yml` every evening). The scheduled loads keep it active for their run only. Record
the monthly cost of capacity and storage from Azure Cost Management in the README.
