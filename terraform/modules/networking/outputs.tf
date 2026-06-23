output "vnet_id" {
  value = azurerm_virtual_network.main.id
}

output "aks_subnet_id" {
  value = azurerm_subnet.aks.id
}

output "services_subnet_id" {
  value = azurerm_subnet.services.id
}
