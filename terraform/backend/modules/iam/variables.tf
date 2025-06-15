variable "aws_region" {
  description = "The AWS region for resources."
  type        = string
}

variable "project_name" {
  description = "The name of the project, used for naming and tagging resources."
  type        = string
}

variable "frontend_s3_bucket_arn" {
  description = "ARN of the S3 bucket created by the frontend stack where Lambdas will write."
  type        = string
}

variable "s3_object_key_prefix_for_lambda_output" {
  description = "S3 object key prefix for Lambda output within the frontend bucket (e.g., 'dynamic_content/'). Must end with a '/' if it's a folder."
  type        = string
  default     = "dynamic_content/"
}

variable "api_key_secret_arns" {
  description = "A list of AWS Secrets Manager secret ARNs that the Lambda functions need access to."
  type        = list(string)
  default     = []
}

variable "bedrock_foundation_models_enabled" {
  description = "Set to true to allow access to all Bedrock foundation models. If false, no Bedrock policy is added by default."
  type        = bool
  default     = true
}

variable "additional_iam_policies" {
  description = "A map of additional IAM policies to attach to the Lambda role. Key is policy name, value is policy JSON."
  type        = map(string)
  default     = {}
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
  default     = {}
}
