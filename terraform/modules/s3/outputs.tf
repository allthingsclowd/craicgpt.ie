# Author: Graham Land & AI
# Date: 2024-07-30
# Filename and Path: terraform/modules/s3/outputs.tf
# Description: Defines outputs for the S3 submodule.

output "bucket_id" {
  description = "The ID of the S3 bucket."
  value       = aws_s3_bucket.website_assets.id
}

output "bucket_arn" {
  description = "The ARN of the S3 bucket."
  value       = aws_s3_bucket.website_assets.arn
}

output "bucket_name" {
  description = "The name of the S3 bucket."
  value       = aws_s3_bucket.website_assets.bucket
}

output "bucket_regional_domain_name" {
  description = "The regional domain name of the S3 bucket."
  value       = aws_s3_bucket.website_assets.bucket_regional_domain_name
}

output "website_endpoint" {
  description = "The S3 bucket website endpoint (e.g., bucketname.s3-website-us-east-1.amazonaws.com)."
  value       = aws_s3_bucket_website_configuration.website_assets_config.website_endpoint
}

output "website_domain" {
  description = "The S3 bucket website domain (e.g., s3-website-us-east-1.amazonaws.com)."
  value       = aws_s3_bucket_website_configuration.website_assets_config.website_domain
}
