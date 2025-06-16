# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/locals.tf
# Version: 0.0.9
# Purpose: Defines local variables for the frontend root module.

locals {
  project_name = "CraicGPT.ie"
  common_tags = {
    Environment = "Development"
    Project     = local.project_name
    ManagedBy   = "Terraform"
    Author      = "Graham Land"
  }
}
