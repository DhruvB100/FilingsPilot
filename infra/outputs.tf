output "api_url" {
  value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "web_url" {
  value = azurerm_storage_account.sa.primary_web_endpoint
}

output "storage_account" {
  value = azurerm_storage_account.sa.name
}

output "function_name" {
  value = azurerm_function_app_flex_consumption.ingest.name
}

output "resource_group" {
  value = azurerm_resource_group.rg.name
}

output "database_url" {
  value     = local.db_url
  sensitive = true
}

output "readonly_password" {
  value     = random_password.pg_readonly.result
  sensitive = true
}

output "cosmos_endpoint" {
  value = azurerm_cosmosdb_account.cosmos.endpoint
}

output "cosmos_key" {
  value     = azurerm_cosmosdb_account.cosmos.primary_key
  sensitive = true
}

output "appinsights_connection_string" {
  value     = azurerm_application_insights.ai.connection_string
  sensitive = true
}
