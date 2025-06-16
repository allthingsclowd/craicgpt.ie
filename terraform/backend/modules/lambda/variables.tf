# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/lambda/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the backend Lambda submodule.

variable "project_name" {
  description = "The name of the project, used for naming and tagging resources."
  type        = string
}

variable "aws_region" {
  description = "The AWS region for resources."
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
  default     = {}
}

variable "lambda_execution_role_arn" {
  description = "ARN of the IAM role to be used by the Lambda functions."
  type        = string
}

variable "s3_target_bucket_arn" {
  description = "ARN of the S3 bucket where Lambda functions will store their output."
  type        = string
}

variable "s3_output_object_key_prefix" {
  description = "Base S3 object key prefix for outputs from these Lambdas (e.g., 'content/'). Each Lambda will get its own sub-prefix."
  type        = string
  default     = "content/"
}

variable "lambda_code_base_path" {
  description = "Base path to the Lambda function code packages (e.g., '../../../lambda_code/backend')."
  type        = string
  default     = "../../../lambda_code/backend" # Adjust if lambda_code is elsewhere relative to this module's root
}

# API Key Secret ARNs - to be referenced in lambda configurations
variable "openai_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the OpenAI API key."
  type        = string
  nullable    = true # Allow null if not all lambdas need it
  default     = null
}

variable "gemini_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the Gemini API key."
  type        = string
  nullable    = true
  default     = null
}

variable "stability_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the Stability AI API key. Used if accessing Stability AI directly."
  type        = string
  sensitive   = true
  nullable    = true
  default     = null
}

variable "anthropic_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret for the Anthropic Claude API key. Used if accessing Anthropic API directly."
  type        = string
  sensitive   = true
  nullable    = true
  default     = null
}
# Add other specific API key secret ARNs if needed, e.g., for other third-party services

# Lambda Configurations
# You can define more specific attributes per lambda if needed.
variable "llm_lambdas_config" {
  description = "Configuration map for LLM Lambda functions. Key is a short identifier (e.g., 'titan-llm')."
  type = map(object({
    handler          = string
    runtime          = string
    source_code_path = string # Relative path under lambda_code_base_path (e.g., "titan_llm_handler")
    description      = optional(string, "LLM processing Lambda function")
    timeout_seconds  = optional(number, 30)
    memory_size_mb   = optional(number, 256)
    environment_variables = optional(map(string), {}) # Specific additional env vars
    bedrock_model_id  = optional(string) # e.g., "amazon.titan-text-express-v1"
    # Symbolic reference to one of the module's root secret ARN variables (e.g., "openai_api_key_secret_arn").
    # The main.tf will use this string to pick the correct var.
    api_key_secret_var_name_ref = optional(string)
  }))
  default = {}
}

variable "image_gen_lambdas_config" {
  description = "Configuration map for Image Generation Lambda functions."
  type = map(object({
    handler          = string
    runtime          = string
    source_code_path = string # Relative path under lambda_code_base_path
    description      = optional(string, "Image generation Lambda function")
    timeout_seconds  = optional(number, 90) # Image gen can take longer
    memory_size_mb   = optional(number, 512)
    environment_variables = optional(map(string), {})
    bedrock_model_id  = optional(string) # e.g., "stability.stable-diffusion-xl-v1"
    api_key_secret_var_name_ref = optional(string)
  }))
  default = {}
}
