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

Repository variables (no secrets: OIDC needs none). Most come from `terraform output`:

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` | outputs `github_client_id`, `tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | the subscription |
| `BW_RESOURCE_GROUP`, `BW_CAPACITY_NAME`, `BW_STORAGE_ACCOUNT` | outputs `resource_group_name`, `fabric_capacity_name`, `storage_account_name` |
| `BW_KEY_VAULT_URI` | output `key_vault_uri` |
| `BW_ALERT_EMAIL`, `BW_USER_AGENT` | alert recipient; SEC User-Agent (name and e-mail) |
| `FABRIC_WORKSPACE_ID_DEV`, `FABRIC_WORKSPACE_ID_PROD` | Fabric stack output `workspace_ids` |
| `FABRIC_SQL_ENDPOINT_DEV` | SQL connection string of `wh_bilanzwerk` in dev (warehouse settings) |
| `FABRIC_GITHUB_CONNECTION_ID` | optional, for Git integration of dev |
| `TF_STATE_RG`, `TF_STATE_ACCOUNT`, `TF_CAPACITY_ADMINS` | state storage from the bootstrap; admins as a JSON list |

Environments: `dev` (pull-request plans, dev deployment) and `prod` with a required reviewer,
so `terraform apply`, the promotion to prod and the scheduled prod loads wait for approval or run
under the protected environment. `github-pages` for the dbt docs.

## Cost

F2 is the smallest pay-as-you-go capacity; it bills per second while active. The capacity is
paused whenever nobody works (`scripts/fabric_capacity.sh pause`, and every evening by
`.github/workflows/capacity-pause.yml`) and resumed by the quarterly load before it starts. The
monthly cost table in the main README is filled from Azure Cost Management at month end; the
budget in this stack alerts at 80 % actual and 100 % forecast.

## Validation status

`azure/` passes `terraform validate` against azurerm 4.80 and azuread 3.9 locally; both stacks
pass `fmt -check` and `validate` in the CI job *Terraform fmt and validate* (Terraform 1.9.8) on
every pull request. `terraform.yml` (plan on pull requests, apply on merge) is skipped until the
repository variables `AZURE_CLIENT_ID` and `TF_STATE_ACCOUNT` exist, because it needs the
bootstrap above.
