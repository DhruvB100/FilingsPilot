variable "subscription_id" {
  type = string
}

variable "location" {
  type    = string
  default = "canadacentral"
}

variable "cosmos_location" {
  type    = string
  default = "swedencentral"
}

variable "prefix" {
  type    = string
  default = "filingspilot"
}

variable "alert_email" {
  type = string
}

variable "budget_amount" {
  type    = number
  default = 5
}

variable "budget_start" {
  description = "first day of the month the budget starts, like 2026-06-01T00:00:00Z"
  type        = string
}

variable "my_ip" {
  description = "my laptop ip so i can load data into postgres"
  type        = string
}

variable "api_image" {
  type    = string
  default = "ghcr.io/dhruvb100/filingspilot-api:latest"
}

# azure openai was created by hand in AI Foundry, just pass the details in
variable "azure_openai_endpoint" {
  type = string
}

variable "azure_openai_api_key" {
  type      = string
  sensitive = true
}

variable "azure_openai_chat_deployment" {
  type    = string
  default = "gpt-5-mini"
}

variable "azure_openai_embed_deployment" {
  type    = string
  default = "text-embedding-3-small"
}

variable "edgar_user_agent" {
  type = string
}

variable "jira_url" {
  type    = string
  default = ""
}

variable "jira_email" {
  type    = string
  default = ""
}

variable "jira_api_token" {
  type      = string
  sensitive = true
  default   = ""
}
