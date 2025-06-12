# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/modules/cloudfront/outputs.tf
# Description: Defines outputs for the CloudFront submodule.

output "distribution_id" {
  description = "The ID of the CloudFront distribution."
  value       = aws_cloudfront_distribution.website_distribution.id
}

output "distribution_domain_name" {
  description = "The domain name of the CloudFront distribution."
  value       = aws_cloudfront_distribution.website_distribution.domain_name
}

output "distribution_arn" {
  description = "The ARN of the CloudFront distribution."
  value       = aws_cloudfront_distribution.website_distribution.arn
}

output "oac_id" {
  description = "The ID of the Origin Access Control."
  value       = aws_cloudfront_origin_access_control.website_assets_oac.id
}
