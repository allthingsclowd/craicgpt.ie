# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/variables.tf
# Description: Declares input variables for the root Terraform configuration.

variable "aws_region" {
  description = "The primary AWS region for deploying resources."
  type        = string
  default     = "eu-west-1"
}

variable "domain_name" {
  description = "The primary domain name for the project (e.g., 'craicgpt.ie'). Used for ACM."
  type        = string
  default     = "craicgpt.ie"
}

variable "cloudfront_aliases" {
  description = "A list of CNAME aliases (e.g., domain names) for the CloudFront distribution."
  type        = list(string)
  default = ["www.craicgpt.ie", "craicgpt.ie", "eddie.craicgpt.ie"]
}

variable "llm_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing the LLM API key."
  type        = string
  sensitive   = true
  default = "value"
}

variable "image_gen_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing the Image Generator API key."
  type        = string
  sensitive   = true
  default = "value"
}

# Variables to control module enablement
variable "enable_acm" {
  description = "Set to true to enable the ACM module for SSL certificate."
  type        = bool
  default     = true
}

variable "enable_s3" {
  description = "Set to true to enable the S3 module for website assets."
  type        = bool
  default     = false
}

variable "enable_lambda" {
  description = "Set to true to enable the Lambda module for content orchestration."
  type        = bool
  default     = false
}

variable "enable_cloudfront" {
  description = "Set to true to enable the CloudFront module for content delivery."
  type        = bool
  default     = false
}

variable "enable_scheduler" {
  description = "Set to true to enable the Scheduler module for daily Lambda triggers."
  type        = bool
  default     = false
}

# S3 Module specific variables
variable "s3_bucket_name_override" {
  description = "Optional: Override the default S3 bucket name. If empty, a name based on project_name is used."
  type        = string
  default     = "craicgpt-ie-development"
}

variable "s3_enable_versioning" {
  description = "Set to true to enable versioning for the S3 bucket."
  type        = bool
  default     = true
}

# Lambda Module specific variables
variable "lambda_function_name_override" {
  description = "Optional: Override the default Lambda function name ('ContentOrchestratorLambda')."
  type        = string
  default     = "ContentOrchestratorLambda"
}

variable "lambda_source_path_override" {
  description = "Allows overriding the default source path for the Lambda function code."
  type        = string
  default     = "../lambda_code/content_orchestrator"
}

variable "lambda_handler_override" {
  description = "Allows overriding the default handler for the Lambda function."
  type        = string
  default     = "index.handler"
}

variable "lambda_runtime_override" {
  description = "Allows overriding the default runtime for the Lambda function."
  type        = string
  default     = "nodejs18.x"
}

# CloudFront Module specific variables
variable "cloudfront_default_root_object" {
  description = "The default object CloudFront serves when the root URL is requested."
  type        = string
  default     = "index.html"
}

variable "cloudfront_price_class" {
  description = "CloudFront price class (e.g., PriceClass_100, PriceClass_200, PriceClass_All)."
  type        = string
  default     = "PriceClass_100"
}

# Scheduler Module specific variables
variable "scheduler_cron_expression" {
  description = "Cron expression for the scheduler that triggers the Lambda."
  type        = string
  default     = "cron(0 1 * * ? *)" # Daily at 01:00 UTC
}

variable "scheduler_timezone" {
  description = "Timezone for the scheduler's cron expression."
  type        = string
  default     = "UTC"
}
