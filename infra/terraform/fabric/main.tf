data "fabric_capacity" "this" {
  display_name = var.capacity_name
}

locals {
  stages = {
    dev  = { display_name = "${var.name} [dev]", description = "Development: Git-connected to branch dev; dbt target dev." }
    prod = { display_name = var.name, description = "Production: only CI deploys here (scripts/fabric_publish.py, approved prod environment)." }
  }

  # Workspace roles per stage (docs/data-classification.md, "Access"). Reporting users read the
  # semantic model through the app/report only; RLS and OLS apply there.
  role_assignments = merge(
    { for s in keys(local.stages) : "${s}-deployer" => { stage = s, id = var.deployer_object_id, type = "ServicePrincipal", role = "Admin" } },
    { for s in keys(local.stages) : "${s}-engineering" => { stage = s, id = var.group_object_ids["Engineering"], type = "Group", role = s == "dev" ? "Admin" : "Member" } },
    { "dev-analyst" = { stage = "dev", id = var.group_object_ids["Analyst"], type = "Group", role = "Contributor" } },
    { "prod-analyst" = { stage = "prod", id = var.group_object_ids["Analyst"], type = "Group", role = "Viewer" } },
    { "prod-reporting" = { stage = "prod", id = var.group_object_ids["Reporting"], type = "Group", role = "Viewer" } },
  )
}

resource "fabric_workspace" "stage" {
  for_each     = local.stages
  display_name = each.value.display_name
  description  = each.value.description
  capacity_id  = data.fabric_capacity.this.id

  identity = {
    type = "SystemAssigned"
  }
}

resource "fabric_lakehouse" "landing" {
  for_each     = local.stages
  display_name = "lh_bilanzwerk"
  description  = "Landing zone: source files and Parquet partitions written by the loaders (ADR-003)."
  workspace_id = fabric_workspace.stage[each.key].id

  configuration = {
    enable_schemas = true
  }
}

resource "fabric_warehouse" "dwh" {
  for_each     = local.stages
  display_name = "wh_bilanzwerk"
  description  = "dbt target: staging, raw vault, business vault, marts (ADR-004, ADR-005)."
  workspace_id = fabric_workspace.stage[each.key].id
}

resource "fabric_workspace_role_assignment" "this" {
  for_each     = local.role_assignments
  workspace_id = fabric_workspace.stage[each.value.stage].id
  role         = each.value.role

  principal = {
    id   = each.value.id
    type = each.value.type
  }
}

# Git integration of the dev workspace (fabric/ folder on branch dev). Needs a GitHub
# connection created once in the portal; skipped until its ID is set.
resource "fabric_workspace_git" "dev" {
  count                   = var.github_connection_id == "" ? 0 : 1
  workspace_id            = fabric_workspace.stage["dev"].id
  initialization_strategy = "PreferRemote"

  git_provider_details = {
    git_provider_type = "GitHub"
    owner_name        = var.github_owner
    repository_name   = var.github_repository
    branch_name       = "dev"
    directory_name    = "/fabric"
  }

  git_credentials = {
    source        = "ConfiguredConnection"
    connection_id = var.github_connection_id
  }
}
