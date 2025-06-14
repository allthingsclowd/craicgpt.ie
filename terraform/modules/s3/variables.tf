# Author: Graham Land & AI
# Date: 2024-07-30
# Filename and Path: terraform/modules/s3/variables.tf
# Description: Defines input variables for the S3 submodule.

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
