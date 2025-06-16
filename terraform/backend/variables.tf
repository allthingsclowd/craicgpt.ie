# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the backend root module.

variable "aws_region" {
  description = "The AWS region for deploying backend resources."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "A short name for the project (e.g., 'craicgpt-backend'). Used for naming resources and in tags."
  type        = string
  default     = "craicgpt-backend"
}

variable "environment" {
  description = "The deployment environment (e.g., 'dev', 'staging', 'prod'). Used for tagging and resource naming."
  type        = string
  default     = "dev"
}

variable "common_tags" {
  description = "Additional common tags to apply to all resources. `Project` and `Environment` tags will be automatically added based on `var.project_name` and `var.environment`."
  type        = map(string)
  default     = {}
}

# Variables for Frontend Terraform Remote State
variable "frontend_terraform_state_bucket" {
  description = "The name of the S3 bucket where the frontend Terraform state file is stored. This variable is mandatory."
  type        = string
  # No default, this must be provided
}

variable "frontend_terraform_state_key" {
  description = "The S3 key for the frontend Terraform state file (e.g., 'env:/app/terraform.tfstate')."
  type        = string
  default     = "terraform.tfstate" # Common default, adjust if needed
}

variable "frontend_terraform_state_region" {
  description = "The AWS region where the frontend Terraform state S3 bucket is located."
  type        = string
  default     = "eu-west-1" # Assume same region, but can be different
}

# API Key Management
variable "openai_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the OpenAI API key. This variable is mandatory if `enable_openai_lambdas` is true."
  type        = string
  sensitive   = true
  # No default, must be provided if OpenAI Lambdas are used
}

variable "gemini_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the Google Gemini API key. This variable is mandatory if `enable_gemini_lambdas` is true."
  type        = string
  sensitive   = true
  # No default, must be provided if Gemini Lambdas are used
}

variable "stability_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the Stability AI API key (if used for image generation)."
  type        = string
  sensitive   = true
  nullable    = true # Allow null if not used
  default     = null
}

# Add other API key secret ARNs as needed, e.g., for Anthropic Claude if used directly
variable "anthropic_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the Anthropic Claude API key (if used directly, not via Bedrock)."
  type        = string
  sensitive   = true
  nullable    = true
  default     = null
}

# Lambda Function Configuration
variable "lambda_code_root_path" {
  description = "Defines the root directory for all backend lambda function code. Passed to the backend lambda module. Default assumes execution from `terraform/backend` directory."
  type        = string
  default     = "../lambda_code/backend" # Relative to terraform/backend directory
}

# These will be used to populate the llm_lambdas_config and image_gen_lambdas_config
# in the main.tf when calling the backend lambda module.

# Module Enablement Flags
variable "enable_bedrock_lambdas" {
  description = "Enable Titan and Claude (Bedrock) Lambda functions and schedules."
  type        = bool
  default     = true
}

variable "enable_openai_lambdas" {
  description = "Enable ChatGPT LLM and Image Gen Lambda functions and schedules."
  type        = bool
  default     = true
}

variable "enable_gemini_lambdas" {
  description = "Enable Gemini LLM and Image Gen Lambda functions and schedules."
  type        = bool
  default     = true
}

variable "enable_stability_lambdas" {
  description = "Enable Stability AI Image Gen Lambda function and schedule (if replacing Claude Image Gen)."
  type        = bool
  default     = true
}

variable "enable_backend_iam_module" {
  description = "Controls whether the backend IAM module is enabled and its resources are created."
  type        = bool
  default     = true
}

variable "enable_backend_lambda_module" {
  description = "Controls whether the backend Lambda module is enabled and its resources are created."
  type        = bool
  default     = false
}

variable "enable_backend_scheduler_module" {
  description = "Controls whether the backend Scheduler module is enabled and its resources are created."
  type        = bool
  default     = false
}
