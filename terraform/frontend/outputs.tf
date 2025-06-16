# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/outputs.tf
# Version: 0.0.9
# Purpose: Declares outputs from the frontend root module.

output "frontend_acm_certificate_arn" {
  description = "The ARN of the ACM certificate (from ACM module)."
  value       = var.enable_acm ? module.acm[0].certificate_arn : null
}

output "frontend_acm_certificate_validation_arn" {
  description = "The ARN of the validated ACM certificate (from ACM module)."
  value       = var.enable_acm ? module.acm[0].certificate_validation_arn : null
}

output "frontend_acm_route53_validation_records_fqdns" {
  description = "The FQDNs of the DNS records used for ACM certificate validation (from ACM module)."
  value       = var.enable_acm ? module.acm[0].route53_validation_records_fqdns : null
}

output "frontend_s3_bucket_id" {
  description = "The ID of the S3 bucket for website assets (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].bucket_id : null
}

output "frontend_s3_bucket_name" {
  description = "The name of the S3 bucket for website assets (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].bucket_name : null
}

output "frontend_s3_bucket_arn" {
  description = "The ARN of the S3 bucket for website assets (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].bucket_arn : null
}

output "frontend_s3_bucket_regional_domain_name" {
  description = "The regional domain name of the S3 bucket (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].bucket_regional_domain_name : null
}

output "frontend_s3_website_endpoint" {
  description = "The S3 bucket website endpoint (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].website_endpoint : null
}

output "frontend_s3_website_domain" {
  description = "The S3 bucket website domain (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].website_domain : null
}

output "frontend_lambda_function_name" {
  description = "The name of the Content Orchestrator Lambda function (from Lambda module)."
  value       = var.enable_lambda ? module.lambda[0].function_name : null
}

output "frontend_lambda_function_arn" {
  description = "The ARN of the Content Orchestrator Lambda function (from Lambda module)."
  value       = var.enable_lambda ? module.lambda[0].function_arn : null
}

output "frontend_lambda_invoke_arn" {
  description = "The Invoke ARN of the Content Orchestrator Lambda function (from Lambda module)."
  value       = var.enable_lambda ? module.lambda[0].invoke_arn : null
}

output "frontend_lambda_role_name" {
  description = "The name of the IAM role for the Content Orchestrator Lambda function (from Lambda module)."
  value       = var.enable_lambda ? module.lambda[0].role_name : null
}

output "frontend_lambda_role_arn" {
  description = "The ARN of the IAM role for the Content Orchestrator Lambda function (from Lambda module)."
  value       = var.enable_lambda ? module.lambda[0].role_arn : null
}

output "frontend_cloudfront_distribution_id" {
  description = "The ID of the CloudFront distribution (from CloudFront module)."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_id : null
}

output "frontend_cloudfront_distribution_domain_name" {
  description = "The domain name of the CloudFront distribution (from CloudFront module)."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_domain_name : null
}

output "frontend_cloudfront_distribution_arn" {
  description = "The ARN of the CloudFront distribution (from CloudFront module)."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_arn : null
}

output "frontend_cloudfront_distribution_hosted_zone_id" {
  description = "The Route 53 Hosted Zone ID for the CloudFront distribution (from CloudFront module)."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_hosted_zone_id : null
}

output "frontend_scheduler_name" {
  description = "The name of the EventBridge Scheduler rule (from Scheduler module)."
  value       = var.enable_scheduler ? module.scheduler[0].schedule_name : null
}

output "frontend_scheduler_arn" {
  description = "The ARN of the EventBridge Scheduler rule (from Scheduler module)."
  value       = var.enable_scheduler ? module.scheduler[0].schedule_arn : null
}

output "frontend_scheduler_iam_role_name" {
  description = "The name of the IAM role for the EventBridge Scheduler rule (from Scheduler module)."
  value       = var.enable_scheduler ? module.scheduler[0].iam_role_name : null
}

output "frontend_scheduler_iam_role_arn" {
  description = "The ARN of the IAM role for the EventBridge Scheduler rule (from Scheduler module)."
  value       = var.enable_scheduler ? module.scheduler[0].iam_role_arn : null
}

output "frontend_s3_uploaded_object_keys" {
  description = "List of S3 object keys uploaded by the frontend-upload module."
  value       = var.enable_frontend_upload && var.enable_s3 ? module.frontend_upload[0].uploaded_object_keys : []
}
