terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                        = "${var.prefix}-kv-${var.suffix}"
  location                    = var.location
  resource_group_name         = var.resource_group_name
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"  # premium only needed for HSM keys
  purge_protection_enabled    = false        # allow easy destroy in dev
  soft_delete_retention_days  = 7           # minimum retention (saves cost edge-cases)

  # Allow GitHub Actions OIDC service principal to read secrets
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = var.github_actions_sp_object_id

    secret_permissions = ["Get", "List"]
  }

  # Allow current Terraform executor to manage secrets
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    key_permissions    = ["Create", "Get", "List", "Delete", "Purge"]
    secret_permissions = ["Set", "Get", "List", "Delete", "Purge"]
  }

  network_acls {
    default_action = "Allow"  # tighten to "Deny" + IP rules in production
    bypass         = ["AzureServices"]
  }

  tags = var.tags
}

# Sample secret — in reality CI writes the DB password here
resource "azurerm_key_vault_secret" "app_secret" {
  name         = "task-api-secret-key"
  value        = var.app_secret_value
  key_vault_id = azurerm_key_vault.main.id

  lifecycle {
    ignore_changes = [value]  # don't overwrite manual rotations
  }
}
