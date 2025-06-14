# Author: Graham Land & AI
# Date: 2024-07-30
# Filename and Path: terraform/modules/frontend-upload/outputs.tf
# Description: Defines outputs for the frontend-upload module.

output "uploaded_object_keys" {
  description = "A list of S3 object keys that were uploaded."
  value       = [for obj in aws_s3_object.website_files : obj.key]
}