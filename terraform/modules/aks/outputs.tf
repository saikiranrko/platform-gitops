output "cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "kube_config" {
  value     = azurerm_kubernetes_cluster.main.kube_config_raw
  sensitive = true
}

output "kubelet_identity_object_id" {
  value       = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  description = "Used to grant AcrPull role to the kubelet managed identity"
}

output "oidc_issuer_url" {
  value       = azurerm_kubernetes_cluster.main.oidc_issuer_url
  description = "Used to configure Workload Identity federation"
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}
