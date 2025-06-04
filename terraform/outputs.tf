# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/outputs.tf
# Description: Declares outputs from the Terraform configuration, providing easy access to important
#              resource identifiers and attributes after deployment. These outputs can be used for
#              reference, in other Terraform configurations, or for automation scripts.
#              Prerequisites: The resources referenced in the 'value' attributes of these outputs
#                             must be defined in other .tf files within this configuration.
#              Validation: Run 'terraform output' after a successful 'terraform apply'. The displayed
#                          values should match the properties of the created AWS resources.

# terraform/outputs.tf

# Output for the ACM Certificate ARN
# This is the ARN of the validated ACM certificate located in us-east-1,
# used by the CloudFront distribution for HTTPS.
output "acm_certificate_arn" {
  description = "The ARN of the validated ACM certificate in us-east-1."
  value       = aws_acm_certificate_validation.site_certificate_validation.certificate_arn
}

# Output for the CloudFront Distribution ID
# This is the unique identifier for the CloudFront distribution.
output "cloudfront_distribution_id" {
  description = "The ID of the CloudFront distribution."
  value       = aws_cloudfront_distribution.website_distribution.id
}

# Output for the CloudFront Distribution Domain Name
# This is the globally unique domain name assigned to the CloudFront distribution (e.g., d12345abcdef.cloudfront.net).
output "cloudfront_distribution_domain_name" {
  description = "The domain name of the CloudFront distribution."
  value       = aws_cloudfront_distribution.website_distribution.domain_name
}

# Output for the S3 Bucket Name
# This is the unique name of the S3 bucket used for storing website assets.
output "s3_bucket_website_assets_name" {
  description = "The name of the S3 bucket for website assets."
  value       = aws_s3_bucket.website_assets.bucket
}

# Output for the S3 Bucket ARN
# This is the Amazon Resource Name (ARN) of the S3 bucket for website assets.
output "s3_bucket_website_assets_arn" {
  description = "The ARN of the S3 bucket for website assets."
  value       = aws_s3_bucket.website_assets.arn
}

# Output for the S3 Bucket Regional Domain Name
# This is the regional domain name of the S3 bucket, used for accessing the bucket directly within its region.
# For CloudFront OAC, CloudFront uses this to access the S3 bucket.
output "s3_bucket_website_assets_regional_domain_name" {
  description = "The regional domain name of the S3 bucket for website assets."
  value       = aws_s3_bucket.website_assets.bucket_regional_domain_name
}

# Output for the Lambda Function Name
# This is the name of the Content Orchestrator Lambda function.
output "lambda_content_orchestrator_function_name" {
  description = "The name of the Content Orchestrator Lambda function."
  value       = module.content_orchestrator_lambda.lambda_function_name
}

# Output for the Lambda Function ARN
# This is the Amazon Resource Name (ARN) of the Content Orchestrator Lambda function.
output "lambda_content_orchestrator_function_arn" {
  description = "The ARN of the Content Orchestrator Lambda function."
  value       = module.content_orchestrator_lambda.lambda_function_arn
}

# Output for the Lambda Function Invoke ARN
# This is the Invoke ARN of the Content Orchestrator Lambda function, used for triggering the function (e.g., by API Gateway).
output "lambda_content_orchestrator_invoke_arn" {
  description = "The Invoke ARN of the Content Orchestrator Lambda function."
  value       = module.content_orchestrator_lambda.lambda_function_invoke_arn
}

# Output for the Scheduler Rule Name
# This is the name of the EventBridge Scheduler rule that triggers daily content generation.
output "scheduler_daily_content_trigger_name" {
  description = "The name of the EventBridge Scheduler rule for daily content."
  value       = aws_scheduler_schedule.daily_content_orchestrator_trigger.name
}

# Output for the Scheduler Rule ARN
# This is the Amazon Resource Name (ARN) of the EventBridge Scheduler rule.
output "scheduler_daily_content_trigger_arn" {
  description = "The ARN of the EventBridge Scheduler rule for daily content."
  value       = aws_scheduler_schedule.daily_content_orchestrator_trigger.arn
}
