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

Then load the data into the new Postgres (no re-embedding, just copy the local db):
```
pg_dump -Fc -d postgresql://filings:filings@localhost:5432/filings -t chunks -t financials -t filings -t companies > filings.dump
DATABASE_URL=$(terraform output -raw database_url) READONLY_PASSWORD=$(terraform output -raw readonly_password) python -m backend.db
pg_restore --data-only --no-owner -d "$(terraform output -raw database_url)" filings.dump
```

## cost
Postgres B1ms is ~$0.55/day, everything else is free tier / pay per use. `terraform destroy` after the demo.
