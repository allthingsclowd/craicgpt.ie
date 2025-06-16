# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/s3/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the frontend S3 submodule.

variable "bucket_name" {
  description = "The name for the S3 bucket. Must be globally unique."
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
  default     = {}
}

variable "enable_versioning" {
  description = "Set to true to enable versioning for the S3 bucket."
  type        = bool
  default     = true
}

variable "index_document" {
  description = "The S3 website configuration index document suffix."
  type        = string
  default     = "index.html"
}

variable "error_document" {
  description = "The S3 website configuration error document key."
  type        = string
  default     = "error.html"
}
