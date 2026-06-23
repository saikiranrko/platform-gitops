variable "prefix" {
  type = string
}

variable "suffix" {
  type    = string
  default = "001"
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "github_actions_sp_object_id" {
  type        = string
  description = "Object ID of the GitHub Actions OIDC service principal — for Key Vault access policy"
}

variable "app_secret_value" {
  type        = string
  sensitive   = true
  description = "Initial value for the app secret. Rotate manually after first deploy."
  default     = "change-me-after-first-deploy"
}

variable "tags" {
  type    = map(string)
  default = {}
}
