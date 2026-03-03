# Author: Graham Land
# File: terraform/frontend/outputs.tf
# Purpose: Outputs from the CraicGPT frontend infrastructure (S3 + CloudFront + ACM).
#
# After applying, copy the output values into GitHub:
#   frontend_s3_bucket_name              → GitHub Variable: S3_BUCKET
#   frontend_cloudfront_distribution_id  → GitHub Secret:   CLOUDFRONT_DISTRIBUTION_ID

output "frontend_acm_certificate_arn" {
  description = "ARN of the ACM SSL certificate."
  value       = var.enable_acm ? module.acm[0].certificate_arn : null
}

output "frontend_acm_certificate_validation_arn" {
  description = "ARN of the validated ACM certificate (used by CloudFront)."
  value       = var.enable_acm ? module.acm[0].certificate_validation_arn : null
}

output "frontend_acm_route53_validation_records_fqdns" {
  description = "FQDNs of the DNS records used for ACM validation."
  value       = var.enable_acm ? module.acm[0].route53_validation_records_fqdns : null
}

output "frontend_s3_bucket_id" {
  description = "S3 bucket ID."
  value       = var.enable_s3 ? module.s3[0].bucket_id : null
}

output "frontend_s3_bucket_name" {
  description = "S3 bucket name — set as GitHub Variable S3_BUCKET."
  value       = var.enable_s3 ? module.s3[0].bucket_name : null
}

output "frontend_s3_bucket_arn" {
  description = "S3 bucket ARN."
  value       = var.enable_s3 ? module.s3[0].bucket_arn : null
}

output "frontend_s3_bucket_regional_domain_name" {
  description = "S3 bucket regional domain name (used by CloudFront as origin)."
  value       = var.enable_s3 ? module.s3[0].bucket_regional_domain_name : null
}

output "frontend_cloudfront_distribution_id" {
  description = "CloudFront distribution ID — set as GitHub Secret CLOUDFRONT_DISTRIBUTION_ID."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_id : null
}

output "frontend_cloudfront_distribution_domain_name" {
  description = "CloudFront distribution domain name."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_domain_name : null
}

output "frontend_cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_arn : null
}

output "frontend_cloudfront_distribution_hosted_zone_id" {
  description = "Route53 hosted zone ID for the CloudFront distribution (used for Alias records)."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_hosted_zone_id : null
}
