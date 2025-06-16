# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/locals.tf
# Version: 0.0.9
# Purpose: Defines local variables for the frontend root module.

locals {
  # project_name is now directly from var.project_name (defined in variables.tf)
  # common_tags will be a merge of explicit common_tags from variables
  # and project-specific identifying tags.
  merged_common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Author      = "Graham Land" # This could also be a variable if it needs to change
    },
    var.common_tags # User-provided tags from variables.tf
  )
}
