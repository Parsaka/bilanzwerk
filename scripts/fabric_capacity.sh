#!/usr/bin/env bash
# Pause, resume or show the Fabric capacity (cost control, ADR-009 and docs/runbook.md).
#
#   scripts/fabric_capacity.sh status|pause|resume
#
# Reads the capacity from the Azure Terraform stack outputs unless BW_CAPACITY_NAME and
# BW_RESOURCE_GROUP are set. Needs the Azure CLI, logged in (az login, or azure/login in CI).
set -euo pipefail

action="${1:-status}"
api="2023-11-01"
tf_dir="$(cd "$(dirname "$0")/../infra/terraform/azure" && pwd)"

rg="${BW_RESOURCE_GROUP:-$(terraform -chdir="$tf_dir" output -raw resource_group_name)}"
name="${BW_CAPACITY_NAME:-$(terraform -chdir="$tf_dir" output -raw fabric_capacity_name)}"
sub="$(az account show --query id -o tsv)"
url="https://management.azure.com/subscriptions/${sub}/resourceGroups/${rg}/providers/Microsoft.Fabric/capacities/${name}"

state() { az rest --method get --url "${url}?api-version=${api}" --query properties.state -o tsv; }

wait_for() {
  local want="$1" now
  for _ in $(seq 1 60); do
    now="$(state)"
    [[ "$now" == "$want" ]] && { echo "${name}: ${now}"; return 0; }
    sleep 10
  done
  echo "${name}: still ${now} after 10 minutes" >&2
  return 1
}

case "$action" in
  status)
    echo "${name}: $(state)"
    ;;
  pause)
    if [[ "$(state)" == "Paused" ]]; then echo "${name}: already paused"; exit 0; fi
    az rest --method post --url "${url}/suspend?api-version=${api}" >/dev/null
    wait_for Paused
    ;;
  resume)
    if [[ "$(state)" == "Active" ]]; then echo "${name}: already active"; exit 0; fi
    az rest --method post --url "${url}/resume?api-version=${api}" >/dev/null
    wait_for Active
    ;;
  *)
    echo "usage: $0 status|pause|resume" >&2
    exit 2
    ;;
esac
