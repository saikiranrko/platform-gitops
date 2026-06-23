variable "prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "aks_subnet_id" {
  type        = string
  description = "Subnet ID for AKS nodes"
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "Log Analytics Workspace resource ID for OMS agent"
}

variable "tags" {
  type    = map(string)
  default = {}
}
