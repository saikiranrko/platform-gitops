# Terraform remote state stored in Azure Blob Storage
# Run scripts/bootstrap.py first to create the storage account and container
terraform {
  backend "azurerm" {
    resource_group_name  = "sai-tfstate-rg"
    storage_account_name = "saitfstate001"    # must be globally unique — change suffix if taken
    container_name       = "tfstate"
    key                  = "dev/terraform.tfstate"
    use_oidc             = true               # no static credentials
  }
}
