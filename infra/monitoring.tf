# budget alert + error alert + dashboard (workbook)

resource "azurerm_monitor_action_group" "email" {
  name                = "${local.name}-alerts"
  resource_group_name = azurerm_resource_group.rg.name
  short_name          = "fpalerts"

  email_receiver {
    name          = "me"
    email_address = var.alert_email
  }
}

resource "azurerm_consumption_budget_resource_group" "budget" {
  name              = "${var.prefix}-budget"
  resource_group_id = azurerm_resource_group.rg.id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.alert_email]
  }
}

# metric alerts are ~$0.10/month, log query alerts cost more, so alert on failed request count
resource "azurerm_monitor_metric_alert" "errors" {
  name                = "${var.prefix}-api-errors"
  resource_group_name = azurerm_resource_group.rg.name
  scopes              = [azurerm_application_insights.ai.id]
  description         = "More than 5 failed API requests in 15 minutes"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = "requests/failed"
    aggregation      = "Count"
    operator         = "GreaterThan"
    threshold        = 5
  }

  action {
    action_group_id = azurerm_monitor_action_group.email.id
  }
}

locals {
  # each tile is a KQL query over app insights. the agent spans have custom attributes (see backend/telemetry.py)
  workbook_queries = [
    {
      title = "p95 latency per question (s)"
      viz   = "timechart"
      query = "dependencies | where name == 'agent.run' | summarize p95_seconds = percentile(duration, 95) / 1000.0 by bin(timestamp, 1h)"
    },
    {
      title = "Cost per question (USD)"
      viz   = "timechart"
      query = "dependencies | where name == 'agent.run' | extend cost = todouble(customDimensions['agent.cost_usd']) | summarize avg_cost = avg(cost), questions = count() by bin(timestamp, 1h)"
    },
    {
      title = "API error rate (%)"
      viz   = "timechart"
      query = "requests | summarize total = count(), failed = countif(success == false) by bin(timestamp, 1h) | extend error_rate = 100.0 * failed / total"
    },
    {
      title = "Tool calls"
      viz   = "barchart"
      query = "dependencies | where name startswith 'tool.' | summarize calls = count(), avg_ms = avg(duration) by name"
    },
    {
      title = "Tokens per question"
      viz   = "table"
      query = "dependencies | where name == 'agent.run' | extend inp = toint(customDimensions['agent.input_tokens']), outp = toint(customDimensions['agent.output_tokens']) | summarize avg(inp), avg(outp), max(inp) by bin(timestamp, 1d)"
    },
  ]
}

resource "azurerm_application_insights_workbook" "dashboard" {
  name                = "8f3c2a1e-6b7d-4e5f-9a0b-1c2d3e4f5a6b"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  display_name        = "FilingsPilot dashboard"
  source_id           = lower(azurerm_application_insights.ai.id)

  data_json = jsonencode({
    version = "Notebook/1.0"
    items = [for i, q in local.workbook_queries : {
      type = 3
      name = "query-${i}"
      content = {
        version       = "KqlItem/1.0"
        query         = q.query
        size          = 0
        title         = q.title
        timeContext   = { durationMs = 604800000 }
        queryType     = 0
        resourceType  = "microsoft.insights/components"
        visualization = q.viz
      }
    }]
    fallbackResourceIds = [azurerm_application_insights.ai.id]
  })
}
