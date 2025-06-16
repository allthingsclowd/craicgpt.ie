# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/acm/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the ACM submodule.

variable "project_name" {
  description = "The name of the project."
  type        = string
}

variable "domain_name" {
  description = "The domain name for which to create the certificate (e.g., 'example.com')."
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
}

variable "subject_alternative_names_list" {
  description = "A list of Subject Alternative Names (SANs) for the certificate. Should include the primary domain_name if it's also an alias."
  type        = list(string)
}
