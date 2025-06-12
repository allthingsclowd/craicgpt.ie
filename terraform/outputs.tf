# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/outputs.tf
# Description: Declares root outputs from the Terraform configuration, referencing submodule outputs.

output "acm_certificate_arn" {
  description = "The ARN of the ACM certificate (from ACM module)."
  value       = var.enable_acm ? module.acm[0].certificate_arn : null
}

output "acm_certificate_validation_arn" {
  description = "The ARN of the validated ACM certificate (from ACM module)."
  value       = var.enable_acm ? module.acm[0].certificate_validation_arn : null
}

output "s3_bucket_name" {
  description = "The name of the S3 bucket for website assets (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].bucket_name : null
}

output "s3_bucket_arn" {
  description = "The ARN of the S3 bucket for website assets (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].bucket_arn : null
}

output "s3_bucket_regional_domain_name" {
  description = "The regional domain name of the S3 bucket (from S3 module)."
  value       = var.enable_s3 ? module.s3[0].bucket_regional_domain_name : null
}

output "lambda_function_name" {
  description = "The name of the Content Orchestrator Lambda function (from Lambda module)."
  value       = var.enable_lambda ? module.lambda[0].function_name : null
}

output "lambda_function_arn" {
  description = "The ARN of the Content Orchestrator Lambda function (from Lambda module)."
  value       = var.enable_lambda ? module.lambda[0].function_arn : null
}

output "cloudfront_distribution_id" {
  description = "The ID of the CloudFront distribution (from CloudFront module)."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_id : null
}

output "cloudfront_distribution_domain_name" {
  description = "The domain name of the CloudFront distribution (from CloudFront module)."
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_domain_name : null
}

output "scheduler_name" {
  description = "The name of the EventBridge Scheduler rule (from Scheduler module)."
  value       = var.enable_scheduler ? module.scheduler[0].schedule_name : null
}

output "scheduler_arn" {
  description = "The ARN of the EventBridge Scheduler rule (from Scheduler module)."
  value       = var.enable_scheduler ? module.scheduler[0].schedule_arn : null
}
