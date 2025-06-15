# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/modules/lambda/variables.tf
# Description: Defines input variables for the Lambda submodule.

variable "project_name" {
  description = "The name of the project."
  type        = string
}

variable "s3_bucket_website_assets_name" {
  description = "Name of the S3 bucket where website assets are stored."
  type        = string
}

variable "s3_bucket_website_assets_arn" {
  description = "ARN of the S3 bucket for website assets."
  type        = string
}

variable "llm_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing the LLM API key."
  type        = string
}

variable "image_gen_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing the Image Generator API key."
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
  default     = {}
}

variable "lambda_source_path_override" {
  description = "Allows overriding the default source path for the Lambda function code."
  type        = string
  default     = "../lambda_code/content_orchestrator" # Original path
}

variable "lambda_handler_override" {
  description = "Allows overriding the default handler for the Lambda function."
  type        = string
  default     = "index.handler" # Original handler
}

variable "lambda_runtime_override" {
  description = "Allows overriding the default runtime for the Lambda function."
  type        = string
  default     = "nodejs18.x" # Original runtime
}

variable "enable_lambda" {
  description = "Set to false to prevent creation of the Lambda function and related resources."
  type        = bool
  default     = true
}

variable "lambda_function_name_override" {
  description = "Allows overriding the default name for the Lambda function."
  type        = string
  default     = "ContentOrchestratorLambda"
}
