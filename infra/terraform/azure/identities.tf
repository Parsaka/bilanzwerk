# --- GitHub Actions: one app registration, OIDC federation, no client secret --------------

resource "azuread_application" "github" {
  display_name = "${var.prefix}-github-actions"
  owners       = [data.azurerm_client_config.current.object_id]
}

resource "azuread_service_principal" "github" {
  client_id = azuread_application.github.client_id
  owners    = [data.azurerm_client_config.current.object_id]
}

locals {
  # Pull requests get read-only plans; main and the prod environment may apply and deploy.
  github_subjects = {
    pull-request = "repo:${var.github_repository}:pull_request"
    main         = "repo:${var.github_repository}:ref:refs/heads/main"
    env-dev      = "repo:${var.github_repository}:environment:dev"
    env-prod     = "repo:${var.github_repository}:environment:prod"
  }
}

resource "azuread_application_federated_identity_credential" "github" {
  for_each       = local.github_subjects
  application_id = azuread_application.github.id
  display_name   = "github-${each.key}"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = each.value
}

resource "azurerm_role_assignment" "github_rg" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.github.object_id
}

resource "azurerm_role_assignment" "github_kv" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azuread_service_principal.github.object_id
}

resource "azurerm_role_assignment" "github_storage" {
  scope                = azurerm_storage_account.landing.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.github.object_id
}

# --- Access groups (data-classification.md, "Access"): least privilege per role ----------

resource "azuread_group" "role" {
  for_each         = toset(["Engineering", "Analyst", "Reporting"])
  display_name     = "sg-${var.prefix}-${lower(each.key)}"
  description      = "Bilanzwerk ${each.key}: see docs/data-classification.md"
  security_enabled = true
  owners           = [data.azurerm_client_config.current.object_id]
}

resource "azurerm_role_assignment" "engineering_storage" {
  scope                = azurerm_storage_account.landing.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_group.role["Engineering"].object_id
}

resource "azurerm_role_assignment" "engineering_kv" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azuread_group.role["Engineering"].object_id
}
