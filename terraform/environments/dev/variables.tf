variable "prefix" {
  type        = string
  default     = "sai"
  description = "Short prefix for all resource names"
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "github_actions_sp_object_id" {
  type        = string
  description = "Object ID of GitHub Actions OIDC service principal — get from: az ad sp show --id <clientId> --query id -o tsv"
}

variable "suffix" {
  type        = string
  default     = "001"
  description = "Numeric suffix for globally unique resource names (ACR, Key Vault, Storage)"
}
