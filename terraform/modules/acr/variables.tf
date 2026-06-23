variable "prefix" {
  type = string
}

variable "suffix" {
  type        = string
  description = "Random suffix to ensure global uniqueness (e.g. '001')"
  default     = "001"
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "aks_kubelet_identity_object_id" {
  type        = string
  description = "Object ID of the AKS kubelet managed identity — for AcrPull role assignment"
}

variable "tags" {
  type    = map(string)
  default = {}
}
