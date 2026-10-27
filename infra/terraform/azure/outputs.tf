output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "fabric_capacity_name" {
  description = "Input for the Fabric stack (variable capacity_name) and scripts/fabric_capacity.sh."
  value       = azurerm_fabric_capacity.this.name
}

output "storage_account_name" {
  value = azurerm_storage_account.landing.name
}

output "key_vault_name" {
  value = azurerm_key_vault.this.name
}

output "github_client_id" {
  description = "GitHub repository variable AZURE_CLIENT_ID (not a secret)."
  value       = azuread_application.github.client_id
}

output "github_service_principal_object_id" {
  description = "Input for the Fabric stack (variable deployer_object_id)."
  value       = azuread_service_principal.github.object_id
}

output "tenant_id" {
  description = "GitHub repository variable AZURE_TENANT_ID."
  value       = data.azurerm_client_config.current.tenant_id
}

output "group_object_ids" {
  description = "Input for the Fabric stack (variable group_object_ids)."
  value       = { for k, g in azuread_group.role : k => g.object_id }
}

output "alert_action_group_id" {
  value = azurerm_monitor_action_group.alerts.id
}
