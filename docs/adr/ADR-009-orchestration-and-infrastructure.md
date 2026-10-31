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

## Amendment (2026-10-27): promotion with fabric-cicd instead of a deployment pipeline

The spec names the Fabric deployment pipeline for the promotion to prod. Building the items
showed two stage-specific values that a deployment pipeline does not rewrite without manual
deployment rules per item: the Direct Lake endpoint of the semantic model and the pipeline
parameters (Key Vault, alert address, stage). Instead, `scripts/fabric_publish.py` publishes the
same Git content to each workspace with Microsoft's `fabric-cicd` library and replaces those
values at publish time; the notebooks find their lakehouse, warehouse and semantic model by name
in the workspace they run in. Promotion to prod is the same command under the GitHub `prod`
environment, which requires an approval. Git integration of the dev workspace stays available for
editing in the Fabric UI.

Consequences: one code path for dev and prod, no IDs in Git, every prod change traceable to a
commit and an approval. The Fabric deployment pipeline UI (compare stages) is not used.
