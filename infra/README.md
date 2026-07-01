# infra

Everything for Azure except Azure OpenAI (made by hand in AI Foundry).

## one time: storage for terraform state

```
az group create -n rg-filingspilot-tfstate -l canadacentral
az storage account create -n <name> -g rg-filingspilot-tfstate --sku Standard_LRS
az storage container create -n tfstate --account-name <name>
```

backend.hcl (not committed):
```
resource_group_name  = "rg-filingspilot-tfstate"
storage_account_name = "<name>"
container_name       = "tfstate"
key                  = "filingspilot.tfstate"
```

## deploy

```
cp terraform.tfvars.example terraform.tfvars   # fill in
terraform init -backend-config=backend.hcl
terraform apply
```

Then copy the local database to Azure (no re-embedding) and deploy the function + frontend:
```
python scripts/copy_to_azure.py "$(terraform output -raw database_url)" "$(terraform output -raw readonly_password)"

sh scripts/package_function.sh
az functionapp deployment source config-zip -g rg-filingspilot -n $(terraform output -raw function_name) --src functions.zip --build-remote true

cd web && VITE_API_URL=$(terraform -chdir=../infra output -raw api_url) npm run build
az storage blob upload-batch --account-name $(terraform -chdir=../infra output -raw storage_account) -d '$web' -s dist --overwrite
```

Notes from deploying on Azure for Students: only 5 regions are allowed by policy (so no Static Web Apps,
the UI is a storage static website) and Cosmos DB had no capacity in canadacentral, so it lives in swedencentral.

## cost
Postgres B1ms is ~$0.55/day, everything else is free tier / pay per use. `terraform destroy` after the demo.
