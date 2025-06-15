# Author: Graham Land & AI
# Date: 2024-07-30
# Filename and Path: terraform/modules/acm/variables.tf
# Description: Defines input variables for the ACM submodule.

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
  default     = {}
}

variable "subject_alternative_names_list" {
  description = "A list of Subject Alternative Names (SANs) for the certificate. Should include the primary domain_name if it's also an alias."
  type        = list(string)
  default     = []
}
