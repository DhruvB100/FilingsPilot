resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.prefix}"
  location = var.location
}

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

resource "random_password" "pg_admin" {
  length  = 24
  special = false
}

resource "random_password" "pg_readonly" {
  length  = 20
  special = false
}

locals {
  name        = "${var.prefix}-${random_string.suffix.result}"
  pg_host     = azurerm_postgresql_flexible_server.pg.fqdn
  db_url      = "postgresql://filingsadmin:${random_password.pg_admin.result}@${local.pg_host}:5432/filings?sslmode=require"
  readonly_db = "postgresql://agent_readonly:${random_password.pg_readonly.result}@${local.pg_host}:5432/filings?sslmode=require"
}

# ---------------- postgres: financial facts + pgvector chunks ----------------
# this is the only thing here that costs real money (~$0.55/day), destroy it after the demo

resource "azurerm_postgresql_flexible_server" "pg" {
  name                          = "${local.name}-pg"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  version                       = "16"
  administrator_login           = "filingsadmin"
  administrator_password        = random_password.pg_admin.result
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  public_network_access_enabled = true

  lifecycle {
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.pg.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "filings" {
  name      = "filings"
  server_id = azurerm_postgresql_flexible_server.pg.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# 0.0.0.0 = "allow azure services" (container app + function)
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure" {
  name             = "allow-azure"
  server_id        = azurerm_postgresql_flexible_server.pg.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "me" {
  name             = "my-laptop"
  server_id        = azurerm_postgresql_flexible_server.pg.id
  start_ip_address = var.my_ip
  end_ip_address   = var.my_ip
}

# ---------------- cosmos db: chat sessions (serverless = pay per request, basically free here) ----------------

resource "azurerm_cosmosdb_account" "cosmos" {
  name                = "${local.name}-cosmos"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.rg.location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "db" {
  name                = "filingspilot"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
}

resource "azurerm_cosmosdb_sql_container" "sessions" {
  name                  = "sessions"
  resource_group_name   = azurerm_resource_group.rg.name
  account_name          = azurerm_cosmosdb_account.cosmos.name
  database_name         = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths   = ["/session_id"]
  partition_key_version = 2
}

# ---------------- storage: raw filings from the daily job + function code ----------------

resource "azurerm_storage_account" "sa" {
  name                     = "${replace(var.prefix, "-", "")}${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

# the react app is hosted as a storage static website. Static Web Apps would be nicer but it only
# runs in 5 regions and my student subscription only allows norway/france/canada/belgium/sweden
resource "azurerm_storage_account_static_website" "web" {
  storage_account_id = azurerm_storage_account.sa.id
  index_document     = "index.html"
  error_404_document = "index.html"
}

resource "azurerm_storage_container" "raw" {
  name                  = "raw-filings"
  storage_account_id    = azurerm_storage_account.sa.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "func" {
  name                  = "function-deploy"
  storage_account_id    = azurerm_storage_account.sa.id
  container_access_type = "private"
}

# ---------------- monitoring ----------------

resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${local.name}-logs"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5 # hard cap so logs can never cost much
}

resource "azurerm_application_insights" "ai" {
  name                = "${local.name}-appinsights"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  workspace_id        = azurerm_log_analytics_workspace.logs.id
  application_type    = "web"
}

# ---------------- container apps: the fastapi api ----------------

resource "azurerm_container_app_environment" "env" {
  name                       = "${local.name}-env"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id
}

resource "azurerm_container_app" "api" {
  name                         = "${var.prefix}-api"
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"

  template {
    min_replicas = 0 # scale to zero when nobody is using it
    max_replicas = 1

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name        = "READONLY_DATABASE_URL"
        secret_name = "readonly-database-url"
      }
      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "azure-openai-key"
      }
      env {
        name        = "COSMOS_KEY"
        secret_name = "cosmos-key"
      }
      env {
        name        = "JIRA_API_TOKEN"
        secret_name = "jira-token"
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = var.azure_openai_endpoint
      }
      env {
        name  = "AZURE_OPENAI_CHAT_DEPLOYMENT"
        value = var.azure_openai_chat_deployment
      }
      env {
        name  = "AZURE_OPENAI_EMBED_DEPLOYMENT"
        value = var.azure_openai_embed_deployment
      }
      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.cosmos.endpoint
      }
      env {
        name  = "COSMOS_DATABASE"
        value = azurerm_cosmosdb_sql_database.db.name
      }
      env {
        name  = "JIRA_URL"
        value = var.jira_url
      }
      env {
        name  = "JIRA_EMAIL"
        value = var.jira_email
      }
      env {
        name  = "JIRA_PROJECT_KEY"
        value = "FP"
      }
      env {
        name  = "CORS_ORIGINS"
        value = "${trimsuffix(azurerm_storage_account.sa.primary_web_endpoint, "/")},http://localhost:5173"
      }
      env {
        name  = "LLM_PROVIDER"
        value = "azure"
      }
      env {
        name  = "MAX_TOKENS_PER_REQUEST"
        value = "40000"
      }
    }
  }

  secret {
    name  = "database-url"
    value = local.db_url
  }
  secret {
    name  = "readonly-database-url"
    value = local.readonly_db
  }
  secret {
    name  = "azure-openai-key"
    value = var.azure_openai_api_key
  }
  secret {
    name  = "cosmos-key"
    value = azurerm_cosmosdb_account.cosmos.primary_key
  }
  secret {
    name  = "jira-token"
    value = var.jira_api_token
  }
  secret {
    name  = "appinsights"
    value = azurerm_application_insights.ai.connection_string
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ---------------- azure function: daily check for new filings ----------------

resource "azurerm_service_plan" "func" {
  name                = "${local.name}-func-plan"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "FC1" # flex consumption, pay per execution
}

resource "azurerm_function_app_flex_consumption" "ingest" {
  name                = "${local.name}-ingest"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  service_plan_id     = azurerm_service_plan.func.id

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.sa.primary_blob_endpoint}${azurerm_storage_container.func.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.sa.primary_access_key
  runtime_name                = "python"
  runtime_version             = "3.12"
  maximum_instance_count      = 40
  instance_memory_in_mb       = 2048

  app_settings = {
    DATABASE_URL                  = local.db_url
    AZURE_OPENAI_ENDPOINT         = var.azure_openai_endpoint
    AZURE_OPENAI_API_KEY          = var.azure_openai_api_key
    AZURE_OPENAI_EMBED_DEPLOYMENT = var.azure_openai_embed_deployment
    EDGAR_USER_AGENT              = var.edgar_user_agent
    DATA_DIR                      = "/tmp/data"
    RAW_BLOB_CONNECTION           = azurerm_storage_account.sa.primary_connection_string
    RAW_BLOB_CONTAINER            = azurerm_storage_container.raw.name
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.ai.connection_string
  }
}
