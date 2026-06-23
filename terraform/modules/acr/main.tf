terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_container_registry" "main" {
  name                = "${var.prefix}acr${var.suffix}"  # must be globally unique, no dashes
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "Basic"  # cheapest tier — $5/month, fine for learning
  admin_enabled       = false    # use managed identity, not admin creds

  tags = var.tags
}

# Grant AKS kubelet identity pull access
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = var.aks_kubelet_identity_object_id
}
