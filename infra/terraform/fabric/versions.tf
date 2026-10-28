terraform {
  required_version = ">= 1.8"

  required_providers {
    fabric = {
      source  = "microsoft/fabric"
      version = "~> 1.3"
    }
  }

  backend "azurerm" {
    use_azuread_auth = true
    key              = "bilanzwerk/fabric.tfstate"
  }
}

# Azure CLI login locally; in GitHub Actions the same OIDC identity as the Azure stack
# (FABRIC_USE_OIDC=true, FABRIC_CLIENT_ID, FABRIC_TENANT_ID).
provider "fabric" {}
