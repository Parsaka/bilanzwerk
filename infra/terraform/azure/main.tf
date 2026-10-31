data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = "rg-${var.prefix}"
  location = var.location
  tags     = var.tags
}

resource "random_string" "suffix" {
  length  = 4
  upper   = false
  special = false
}

# --- Storage: landing zone for raw downloads (archive of every source file, ADR-002) ---------

resource "azurerm_storage_account" "landing" {
  name                            = "st${var.prefix}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  tags                            = var.tags

  blob_properties {
    delete_retention_policy {
      days = 14
    }
    container_delete_retention_policy {
      days = 14
    }
  }
}

resource "azurerm_storage_container" "landing" {
  for_each              = toset(["raw", "archive"])
  name                  = each.key
  storage_account_id    = azurerm_storage_account.landing.id
  container_access_type = "private"
}

# Source zips are kept for reproducibility but rarely read: cool after 30 days.
resource "azurerm_storage_management_policy" "landing" {
  storage_account_id = azurerm_storage_account.landing.id

  rule {
    name    = "archive-to-cool"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["archive/"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 30
      }
    }
  }
}

# --- Key Vault: the only place for configuration that is not in Git ------------------------

resource "azurerm_key_vault" "this" {
  name                       = "kv-${var.prefix}-${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = var.tags
}

resource "azurerm_role_assignment" "kv_admin_deployer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "sec_user_agent" {
  name         = "sec-user-agent"
  value        = var.sec_user_agent
  key_vault_id = azurerm_key_vault.this.id
  content_type = "text/plain"
  depends_on   = [azurerm_role_assignment.kv_admin_deployer]
}

# --- Fabric capacity -----------------------------------------------------------------------

resource "azurerm_fabric_capacity" "this" {
  name                   = "fc${var.prefix}${random_string.suffix.result}"
  resource_group_name    = azurerm_resource_group.this.name
  location               = azurerm_resource_group.this.location
  administration_members = var.capacity_admins
  tags                   = var.tags

  sku {
    name = var.capacity_sku
    tier = "Fabric"
  }
}
