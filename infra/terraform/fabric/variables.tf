variable "capacity_name" {
  description = "Fabric capacity created by the Azure stack (output fabric_capacity_name)."
  type        = string
}

variable "deployer_object_id" {
  description = "Object ID of the GitHub Actions service principal (Azure stack output github_service_principal_object_id)."
  type        = string
}

variable "group_object_ids" {
  description = "Entra ID groups by role: Engineering, Analyst, Reporting (Azure stack output group_object_ids)."
  type        = map(string)

  validation {
    condition     = alltrue([for k in ["Engineering", "Analyst", "Reporting"] : contains(keys(var.group_object_ids), k)])
    error_message = "group_object_ids needs the keys Engineering, Analyst and Reporting."
  }
}

variable "github_connection_id" {
  description = "ID of the Fabric connection to GitHub used by Git integration (created once in the Fabric portal with a fine-grained token). Empty: no Git integration."
  type        = string
  default     = ""
}

variable "github_owner" {
  type    = string
  default = "Parsaka"
}

variable "github_repository" {
  type    = string
  default = "bilanzwerk"
}

variable "name" {
  type    = string
  default = "Bilanzwerk"
}
