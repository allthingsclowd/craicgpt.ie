# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/modules/lambda/outputs.tf
# Description: Defines outputs for the Lambda submodule.

output "function_name" {
  description = "The name of the Lambda function."
  value       = module.generic_lambda.lambda_function_name
}

output "function_arn" {
  description = "The ARN of the Lambda function."
  value       = module.generic_lambda.lambda_function_arn
}

output "invoke_arn" {
  description = "The Invoke ARN of the Lambda function."
  value       = module.generic_lambda.lambda_function_invoke_arn
}

output "role_name" {
  description = "The name of the IAM role created for the Lambda function."
  value       = module.generic_lambda.lambda_role_name
}

output "role_arn" {
  description = "The ARN of the IAM role created for the Lambda function."
  value       = module.generic_lambda.lambda_role_arn
}
