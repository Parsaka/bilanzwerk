# Runbook

How to run, recover and rerun. Commands assume the repo root and `uv sync --all-extras`.

## Environment variables

| Variable | Meaning | Example |
|---|---|---|
| `BW_DATA_ROOT` | Landing zone and local warehouse folder | `./data` (local), `/lakehouse/default/Files` (Fabric notebook) |
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

## New SEC quarter

1. `quarterly-load.yml` (manual or scheduled) starts the Fabric master pipeline with
   `load_quarter=2026q4`.
2. The FSDS loader lands only that quarter; dbt staging filters to it with
   `--vars '{load_quarter: 2026q4}'`; vault models insert only new keys and changed attributes.
3. The job summary shows row counts and the data quality pass rate.

## Rerun one quarter (incident drill)

Scenario: the SEC renames a column in one quarter file (e.g. `ddate` → `date_end`).

1. The loader's column contract fails before anything lands:
   `ContractError: num.txt is missing required columns: ['ddate']`; a `failed` row is written to
   the manifest, the pipeline's failure activity sends the alert e-mail.
2. Fix: add the rename to the reader (`ingestion/sec_fsds.py`, `read_table`), add a test with a
   fixture file in the new layout, merge.
3. Rerun only that quarter: `uv run bilanzwerk sec-fsds --start 2026q4 --end 2026q4`, then
   `dbt build --vars '{load_quarter: 2026q4}'`. The landing partition is replaced, the vault
   inserts the missing rows, nothing else changes.
4. Write the drill down in `docs/incident-drill.md` with the timings.

The pytest `test_renamed_column_is_caught_by_contract` reproduces step 1 on every pull request.

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
(Fabric pipeline "Office 365 Outlook" activity on failure; see `fabric/pipelines/`).

## Costs

Start on the Fabric trial; afterwards the smallest pay-as-you-go F capacity, paused whenever
nobody works (`infra/terraform` creates it; `scripts/fabric_capacity.sh pause|resume`). Record
the monthly cost of capacity and storage in the README.
