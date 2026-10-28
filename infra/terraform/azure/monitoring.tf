# --- Alerts and cost --------------------------------------------------------------------------

resource "azurerm_monitor_action_group" "alerts" {
  name                = "ag-${var.prefix}"
  resource_group_name = azurerm_resource_group.this.name
  short_name          = substr(var.prefix, 0, 12)
  tags                = var.tags

  email_receiver {
    name                    = "owner"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

resource "azurerm_consumption_budget_resource_group" "monthly" {
  name              = "budget-${var.prefix}"
  resource_group_id = azurerm_resource_group.this.id
  amount            = var.monthly_budget
  time_grain        = "Monthly"

  time_period {
    start_date = "2026-11-01T00:00:00Z"
  }

  notification {
    enabled        = true
    operator       = "GreaterThan"
    threshold      = 80
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.alerts.id]
  }

  notification {
    enabled        = true
    operator       = "GreaterThan"
    threshold      = 100
    threshold_type = "Forecasted"
    contact_groups = [azurerm_monitor_action_group.alerts.id]
  }
}
