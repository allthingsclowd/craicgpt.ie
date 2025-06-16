# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/frontend-upload/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the frontend-upload submodule.

variable "s3_bucket_id" {
  description = "The ID of the S3 bucket to upload files to."
  type        = string
}

variable "frontend_directory" {
  description = "The local directory path containing the frontend assets to upload."
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to S3 objects, if any. Currently not used for objects."
  type        = map(string)
}

variable "enable_upload" {
  description = "Set to false to disable the frontend content upload."
  type        = bool
}