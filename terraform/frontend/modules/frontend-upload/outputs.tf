# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/frontend-upload/outputs.tf
# Version: 0.0.9
# Purpose: Declares outputs from the frontend-upload submodule.

output "uploaded_object_keys" {
  description = "A list of S3 object keys that were uploaded."
  value       = [for obj in aws_s3_object.website_files : obj.key]
}