# Author: Graham Land & AI
# Date: 2024-07-30
# Filename and Path: terraform/modules/frontend-upload/variables.tf
# Description: Defines input variables for the frontend-upload module.

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
  default     = {}
}

variable "enable_upload" {
  description = "Set to false to disable the frontend content upload."
  type        = bool
  default     = true
}