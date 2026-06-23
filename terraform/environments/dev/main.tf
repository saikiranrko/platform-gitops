terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true   # makes destroy clean in dev
      recover_soft_deleted_key_vaults = true
    }
  }
  use_oidc = true  # GitHub Actions authenticates via OIDC, no static secrets
}

locals {
  common_tags = {
    environment = var.environment
    project     = "platform-gitops"
    managed_by  = "terraform"
    owner       = "saikiranrko"
  }
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = "${var.prefix}-platform-rg"
  location = var.location
  tags     = local.common_tags
}

# ---------------------------------------------------------------------------
# Networking Layer
# ---------------------------------------------------------------------------
module "networking" {
  source = "../../modules/networking"

  prefix              = var.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

# ---------------------------------------------------------------------------
# AKS Cluster
# ---------------------------------------------------------------------------
module "aks" {
  source = "../../modules/aks"

  prefix                     = var.prefix
  location                   = var.location
  resource_group_name        = azurerm_resource_group.main.name
  aks_subnet_id              = module.networking.aks_subnet_id
  log_analytics_workspace_id = module.aks.log_analytics_workspace_id
  tags                       = local.common_tags

  depends_on = [module.networking]
}

# ---------------------------------------------------------------------------
# Container Registry
# ---------------------------------------------------------------------------
module "acr" {
  source = "../../modules/acr"

  prefix                         = var.prefix
  suffix                         = var.suffix
  location                       = var.location
  resource_group_name            = azurerm_resource_group.main.name
  aks_kubelet_identity_object_id = module.aks.kubelet_identity_object_id
  tags                           = local.common_tags

  depends_on = [module.aks]
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------
module "keyvault" {
  source = "../../modules/keyvault"

  prefix                      = var.prefix
  suffix                      = var.suffix
  location                    = var.location
  resource_group_name         = azurerm_resource_group.main.name
  github_actions_sp_object_id = var.github_actions_sp_object_id
  tags                        = local.common_tags
}

# ---------------------------------------------------------------------------
# Outputs (used by CI/CD and scripts)
# ---------------------------------------------------------------------------
output "acr_login_server" {
  value = module.acr.login_server
}

output "aks_cluster_name" {
  value = module.aks.cluster_name
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "oidc_issuer_url" {
  value = module.aks.oidc_issuer_url
}

output "key_vault_uri" {
  value = module.keyvault.key_vault_uri
}
