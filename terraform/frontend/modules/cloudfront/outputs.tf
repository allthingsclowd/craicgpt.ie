# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/cloudfront/outputs.tf
# Version: 0.0.9
# Purpose: Declares outputs from the CloudFront submodule.

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

output "distribution_hosted_zone_id" {
  description = "The Route 53 Hosted Zone ID for the CloudFront distribution (for Alias records)."
  value       = aws_cloudfront_distribution.website_distribution.hosted_zone_id
}

output "oac_id" {
  description = "The ID of the Origin Access Control."
  value       = aws_cloudfront_origin_access_control.website_assets_oac.id
}
