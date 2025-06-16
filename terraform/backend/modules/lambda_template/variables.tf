# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/lambda_template/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the backend Lambda Template submodule.

variable "project_name" {
  description = "The name of the project. Used for deriving resource names or tags."
  type        = string
}

variable "lambda_function_name_override" {
  description = "Specific name for the Lambda function."
  type        = string
}

variable "lambda_description" {
  description = "Description for the Lambda function."
  type        = string
}

variable "lambda_source_path_override" {
  description = "Source path for the Lambda function code (e.g., a local directory or an S3 object)."
  type        = string
}

variable "lambda_handler_override" {
  description = "Handler for the Lambda function (e.g., 'index.handler')."
  type        = string
}

variable "lambda_runtime_override" {
  description = "Runtime for the Lambda function (e.g., 'nodejs18.x', 'python3.9')."
  type        = string
}

variable "lambda_timeout" {
  description = "Timeout for the Lambda function in seconds."
  type        = number
}

variable "lambda_memory_size" {
  description = "Memory size for the Lambda function in MB."
  type        = number
}

variable "existing_lambda_role_arn" {
  description = "ARN of an existing IAM role to use for the Lambda function. If null, a new role will be created by this module."
  type        = string
}

variable "lambda_environment_variables" {
  description = "A map of environment variables to set for the Lambda function."
  type        = map(string)
}

variable "s3_target_bucket_arn" {
  description = "ARN of the S3 bucket where the Lambda will store output. Required if Lambda needs S3 write access for the role created by this module."
  type        = string
}

variable "s3_object_key_prefix" {
  description = "S3 object key prefix for Lambda output (e.g., 'content/'). Include trailing slash if it's a folder."
  type        = string
}

variable "secret_arns_to_access" {
  description = "A list of AWS Secrets Manager secret ARNs that the Lambda function needs access to (for role created by this module)."
  type        = list(string)
}

variable "bedrock_model_arns_to_access" {
  description = "A list of specific Bedrock model ARNs the Lambda needs access to (for role created by this module, e.g., ['arn:aws:bedrock:::model/anthropic.claude-v2']). Use ['arn:aws:bedrock:REGION::foundation-model/*'] for all models in the region, but be specific if possible."
  type        = list(string)
}

variable "enable_lambda" {
  description = "Set to false to prevent creation of the Lambda function and related resources."
  type        = bool
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
}

// Kept for potential use in var.lambda_environment_variables if needed by specific lambda functions,
// but S3 permissions will be primarily governed by s3_target_bucket_arn and s3_object_key_prefix if role is created by this module.
variable "s3_bucket_website_assets_name" {
  description = "Name of an S3 bucket, potentially for environment variables. Note: S3 permissions for module-created role use s3_target_bucket_arn."
  type        = string
}

// This variable is less generic. If an S3 ARN is needed for env vars, it should be passed via lambda_environment_variables.
// However, if many lambdas use this specific ARN for a common purpose, it could be kept.
// For now, commenting out as direct S3 permissions are handled by s3_target_bucket_arn.
// variable "s3_bucket_website_assets_arn" {
//   description = "ARN of the S3 bucket for website assets. (Consider if needed, or pass via env vars)"
//   type        = string
//   default     = null
// }

# Removed variables (now covered by more generic ones):
# variable "llm_api_key_secret_arn" { ... }
# variable "image_gen_api_key_secret_arn" { ... }
