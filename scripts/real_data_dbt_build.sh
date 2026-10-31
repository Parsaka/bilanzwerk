#!/usr/bin/env bash
# dbt build for the real-data run (.github/workflows/real-data-run.yml).
#
#   scripts/real_data_dbt_build.sh <label> [dbt selector]
#
# The builds after MDM and after the model select only what depends on the new input
# (source:mdm+, source:analysis+): rebuilding the whole business vault again would cost an
# hour and fill the runner's disk.
#
# Failing tests are stored (--store-failures) and the run goes on: the models the failures
# skipped are built without tests, so one run shows every problem down the chain instead of
# one per run. Such a run is marked (data/results/DBT_TESTS_FAILED) and the job fails at the
# end; its numbers are diagnostics, never results.
set -uo pipefail
label="$1"
select=()
if [ -n "${2:-}" ]; then select=(--select "$2"); fi
vars="{load_quarter: ${LAST_QUARTER}}"

if uv run dbt build --project-dir dbt --store-failures --vars "$vars" "${select[@]}"; then
  exit 0
fi
mkdir -p data/results
cp dbt/target/run_results.json "data/results/dbt_run_results_${label}.json"
echo "$label" >> data/results/DBT_TESTS_FAILED
echo "DBT_TESTS_FAILED=1" >> "$GITHUB_ENV"
echo "::error::dbt build ($label) failed; building the skipped models without tests, results of this run are diagnostic only"
uv run dbt run --project-dir dbt --vars "$vars" "${select[@]}"
