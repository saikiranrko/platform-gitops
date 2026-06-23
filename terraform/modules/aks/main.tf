terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = "${var.prefix}-aks"
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = "${var.prefix}-aks"

  # --- Cost optimization: smallest viable node ---
  default_node_pool {
    name                = "system"
    node_count          = 1             # single node for dev/learning
    vm_size             = "Standard_D2s_v7" # 2 vCPU, 4GB RAM — ~$30/month
    vnet_subnet_id      = var.aks_subnet_id
    os_disk_size_gb     = 30            # minimum disk
    type                = "VirtualMachineScaleSets"

    # Enable auto-scaler but cap at 1 node to control costs
    enable_auto_scaling = true
    min_count           = 1
    max_count           = 2

    upgrade_settings {
      max_surge = "10%"
    }
  }

  # Use system-assigned managed identity (no SP credential rotation needed)
  identity {
    type = "SystemAssigned"
  }

  # OIDC + Workload Identity for pods to access Azure services without secrets
  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  # Azure CNI for better enterprise networking
  network_profile {
    network_plugin    = "azure"
    network_policy    = "calico"
    load_balancer_sku = "standard"
    service_cidr      = "10.100.0.0/16"
    dns_service_ip    = "10.100.0.10"
  }

  # Azure Monitor integration (sends logs to Log Analytics)
  oms_agent {
    log_analytics_workspace_id = var.log_analytics_workspace_id
  }

  # Key Vault secrets injection via CSI driver
  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  # Kubernetes RBAC
  role_based_access_control_enabled = true

  # Free tier control plane (saves ~$73/month vs Standard)
  sku_tier = "Free"

  tags = var.tags

  lifecycle {
    ignore_changes = [
      default_node_pool[0].node_count  # auto-scaler manages this
    ]
  }
}

# Log Analytics Workspace for AKS monitoring
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.prefix}-law"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30  # minimum; default 90 costs more

  tags = var.tags
}
