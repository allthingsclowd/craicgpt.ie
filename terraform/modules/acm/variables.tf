# Author: Graham Land & AI
# Date: YYYY-MM-DD
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

variable "aws_provider_alias_us_east_1" {
  description = "Alias for the AWS provider configured for us-east-1, needed for ACM certificate."
  type        = string
  default     = "aws.us_east_1_acm" # Defaulting to the alias used in the original acm.tf
}
