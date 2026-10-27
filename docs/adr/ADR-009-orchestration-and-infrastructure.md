# ADR-009: Orchestration, CI/CD and infrastructure

- Status: accepted
- Date: 2026-10-27

## Decision

- Orchestration in **Fabric Data Factory**: one pipeline per source plus a master pipeline
  (load, dbt build, semantic model refresh). Triggers: FSDS quarterly, GLEIF and ECB daily,
  submissions weekly. Definitions in `fabric/`.
- **GitHub Actions** for CI/CD only: `ci.yml` on every pull request (ruff, pytest, SQLFluff,
  dbt build on the fixture, contract check, leakage test, BPA on the PBIP model),
  `dbt-build.yml` on merge (dev warehouse, dbt docs to GitHub Pages, promotion to prod),
  `quarterly-load.yml`, `terraform.yml`. Azure login with OIDC; no stored secrets.
- **Terraform** for Azure resources (resource group, storage, key vault, Fabric capacity,
  identities) and Fabric items where the `microsoft/fabric` provider supports them
  (workspaces, lakehouse, warehouse, role assignments, Git connection). Everything else is a
  documented script.

## Consequences

The Fabric capacity is paused whenever nobody works (cost); the pause schedule and the monthly
cost go into the README.
