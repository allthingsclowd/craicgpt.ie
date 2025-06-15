variable "aws_region" {
  description = "The AWS region for deploying backend resources."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "The name of the project (e.g., 'craicgpt'). Used for naming and tagging."
  type        = string
  default     = "craicgpt"
}

variable "common_tags" {
  description = "Common tags to apply to all resources created by this backend configuration."
  type        = map(string)
  default = {
    Terraform   = "true"
    Environment = "dev"
    Project     = "CraicGPT-Backend"
  }
}

# Variables for Frontend Terraform Remote State
variable "frontend_terraform_state_bucket" {
  description = "The name of the S3 bucket where the frontend Terraform state file is stored."
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

# API Key Secret ARNs from AWS Secrets Manager
variable "openai_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the OpenAI API key."
  type        = string
  sensitive   = true
  # No default, must be provided if OpenAI Lambdas are used
}

variable "gemini_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the Google Gemini API key."
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

# Configuration for Lambda functions
# These will be used to populate the llm_lambdas_config and image_gen_lambdas_config
# in the main.tf when calling the backend lambda module.

variable "lambda_code_root_path" {
  description = "Defines the root directory for all backend lambda function code. Passed to the backend lambda module."
  type        = string
  default     = "../lambda_code/backend" # Relative to terraform/backend directory
}

# Placeholder for actual Lambda code zip files if pre-built.
# For now, the lambda module expects source_code_path to be a directory.
# variable "titan_llm_lambda_zip_path" {
#   description = "Path to the pre-built ZIP file for the Titan LLM Lambda."
#   type        = string
#   default     = "" # Example: "lambda_zips/titan_llm.zip"
# }

# Control flags for enabling/disabling groups of Lambdas if needed
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
  default     = true
}

variable "enable_backend_scheduler_module" {
  description = "Controls whether the backend Scheduler module is enabled and its resources are created."
  type        = bool
  default     = true
}
