terraform {
  required_version = ">= 1.6"

  # state lives in a storage account outside this config (see infra/README.md),
  # init with: terraform init -backend-config=backend.hcl
  backend "azurerm" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {
    resource_group {
      # so terraform destroy actually works after the demo even if azure added stuff to the group
      prevent_deletion_if_contains_resources = false
    }
  }
  subscription_id = var.subscription_id
}
