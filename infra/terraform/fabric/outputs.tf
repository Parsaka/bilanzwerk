output "workspace_ids" {
  description = "GitHub repository variables FABRIC_WORKSPACE_ID_DEV / _PROD."
  value       = { for k, w in fabric_workspace.stage : k => w.id }
}

output "warehouse_ids" {
  value = { for k, w in fabric_warehouse.dwh : k => w.id }
}

output "lakehouse_ids" {
  value = { for k, l in fabric_lakehouse.landing : k => l.id }
}
