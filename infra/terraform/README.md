# Infrastructure (Terraform)

Two stacks, applied in this order:

| Stack | Provider | Creates |
|---|---|---|
| `azure/` | azurerm, azuread | resource group, landing storage (ADLS Gen2, `raw` and `archive`), Key Vault (RBAC) with the SEC User-Agent, Fabric capacity (F2 by default), GitHub OIDC app with federated credentials, Engineering/Analyst/Reporting groups, alert action group, monthly budget |
| `fabric/` | microsoft/fabric | dev and prod workspaces on the capacity, lakehouse and warehouse in each, workspace roles, Git integration of dev (once a GitHub connection exists) |

They are separate because the Fabric provider needs the capacity to exist and because a
problem in the younger Fabric provider must not block changes to the Azure resources (ADR-009).

## Bootstrap (once, from your PC)

The first apply runs with your own login, because the GitHub identity does not exist yet.

```bash
az login
SUB=$(az account show --query id -o tsv)

# 1. Storage for the Terraform state (outside Terraform on purpose)
az group create -n rg-bilanzwerk-tfstate -l germanywestcentral
az storage account create -n stbilanzwerktfstate -g rg-bilanzwerk-tfstate -l germanywestcentral \
  --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false
az storage container create -n tfstate --account-name stbilanzwerktfstate --auth-mode login
az role assignment create --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --role "Storage Blob Data Contributor" \
  --scope "$(az storage account show -n stbilanzwerktfstate -g rg-bilanzwerk-tfstate --query id -o tsv)"

# 2. Azure stack
cd infra/terraform/azure
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars        # subscription_id, admins, e-mail
export TF_VAR_sec_user_agent="Parsa Kamali parsa.kamali.data@gmail.com"
terraform init -backend-config=backend.hcl
terraform apply

# 3. The GitHub identity also writes the state from CI
az role assignment create --assignee "$(terraform output -raw github_service_principal_object_id)" \
  --role "Storage Blob Data Contributor" \
  --scope "$(az storage account show -n stbilanzwerktfstate -g rg-bilanzwerk-tfstate --query id -o tsv)"
```

Fabric needs two settings in the admin portal before the second stack: *Service principals can
use Fabric APIs* (tenant setting, limited to the group that holds the GitHub service principal)
and, for Git integration, a GitHub connection created under *Manage connections and gateways*
with a fine-grained token (contents read/write on this repository only).

```bash
cd ../fabric
cp ../azure/backend.hcl backend.hcl
terraform init -backend-config=backend.hcl
terraform apply \
  -var "capacity_name=$(terraform -chdir=../azure output -raw fabric_capacity_name)" \
  -var "deployer_object_id=$(terraform -chdir=../azure output -raw github_service_principal_object_id)" \
  -var "group_object_ids=$(terraform -chdir=../azure output -json group_object_ids)" \
  -var "github_connection_id=<connection id or empty>"
```

## GitHub repository settings

Variables (not secrets; OIDC needs no stored secret): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`, `TF_STATE_RG`, `TF_STATE_ACCOUNT`, `FABRIC_WORKSPACE_ID_DEV`,
`FABRIC_WORKSPACE_ID_PROD`, `FABRIC_DEPLOYMENT_PIPELINE_ID`, `FABRIC_SQL_ENDPOINT_DEV`,
`FABRIC_MASTER_PIPELINE_ID`, `BW_USER_AGENT`. Environments `dev` and `prod`; `prod` with a
required reviewer, so `terraform apply` and the promotion to prod wait for approval.

## Cost

F2 is the smallest pay-as-you-go capacity; it bills per second while active. The capacity is
paused whenever nobody works (`scripts/fabric_capacity.sh pause`, and every evening by
`.github/workflows/capacity-pause.yml`) and resumed by the quarterly load before it starts. The
monthly cost table in the main README is filled from Azure Cost Management at month end; the
budget in this stack alerts at 80 % actual and 100 % forecast.

## Validation status

`azure/` passes `terraform validate` against azurerm 4.80 and azuread 3.9. `fabric/` is
formatted but was not validated here, because the provider registry was not reachable from the
build environment; `terraform.yml` validates both stacks on every pull request.
