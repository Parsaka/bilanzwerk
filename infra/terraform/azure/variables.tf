variable "subscription_id" {
  description = "Azure subscription that holds the project."
  type        = string
}

variable "location" {
  description = "Azure region. Germany West Central keeps the data in Germany."
  type        = string
  default     = "germanywestcentral"
}

variable "prefix" {
  description = "Short name used in every resource name."
  type        = string
  default     = "bilanzwerk"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.prefix))
    error_message = "prefix: 3 to 12 lower-case letters or digits, starting with a letter (storage and capacity names)."
  }
}

variable "capacity_sku" {
  description = "Fabric capacity size. F2 is the smallest pay-as-you-go size (ADR-003); it is paused when idle."
  type        = string
  default     = "F2"

  validation {
    condition     = contains(["F2", "F4", "F8", "F16", "F32", "F64"], var.capacity_sku)
    error_message = "capacity_sku must be one of F2, F4, F8, F16, F32, F64."
  }
}

variable "capacity_admins" {
  description = "User principal names (e-mail form) of the Fabric capacity administrators."
  type        = list(string)
}

variable "github_repository" {
  description = "owner/name of the GitHub repository whose workflows may log in with OIDC."
  type        = string
  default     = "Parsaka/bilanzwerk"
}

variable "alert_email" {
  description = "Receives pipeline, data quality and budget alerts."
  type        = string
}

variable "monthly_budget" {
  description = "Monthly cost budget for the resource group in the billing currency; alerts at 80 % (actual) and 100 % (forecast)."
  type        = number
  default     = 60
}

variable "sec_user_agent" {
  description = "Declared User-Agent for SEC downloads: name and e-mail of the person running the loader."
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Tags on every resource."
  type        = map(string)
  default = {
    project    = "bilanzwerk"
    managed_by = "terraform"
    data_class = "public-company-data"
  }
}
