# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/locals.tf
# Description: Defines common local variables used across the Terraform configuration.

locals {
  project_name = "CraicGPT.ie"
  common_tags = {
    Environment = "production"
    Project     = local.project_name
    ManagedBy   = "Terraform"
    Author      = "Graham Land & AI"
  }
}
