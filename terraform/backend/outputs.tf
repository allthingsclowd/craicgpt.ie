# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/outputs.tf
# Version: 0.0.9
# Purpose: Declares outputs from the backend root module.

output "backend_lambda_execution_role_arn" {
  description = "ARN of the IAM role used by the backend Lambda functions."
  value       = var.enable_backend_iam_module ? module.backend_iam[0].lambda_execution_role_arn : null
}

output "backend_lambda_execution_role_name" {
  description = "Name of the IAM role used by the backend Lambda functions."
  value       = var.enable_backend_iam_module ? module.backend_iam[0].lambda_execution_role_name : null
}

output "backend_lambda_functions" {
  description = "Detailed information about each created backend Lambda function, exposing all outputs from the underlying lambda_template instances."
  value       = var.enable_backend_lambda_module && var.enable_backend_iam_module ? module.backend_lambda[0].lambda_function_details : {}
}

output "backend_lambda_functions_summary" {
  description = "Summary map of created backend Lambda functions, keyed by their identifier, providing key details like ARN, name, and invoke ARN."
  value       = var.enable_backend_lambda_module && var.enable_backend_iam_module ? module.backend_lambda[0].lambda_functions : {}
}

output "backend_schedules" {
  description = "Detailed information about each created EventBridge schedule for backend Lambdas, exposing all outputs from the underlying scheduler_template instances."
  value       = var.enable_backend_scheduler_module && var.enable_backend_lambda_module && var.enable_backend_iam_module ? module.backend_scheduler[0].schedule_details : {}
}

output "backend_schedules_summary" {
  description = "Summary map of created EventBridge schedules for backend Lambdas, keyed by their identifier, providing key details like ARN, name, and IAM role ARN."
  value       = var.enable_backend_scheduler_module && var.enable_backend_lambda_module && var.enable_backend_iam_module ? module.backend_scheduler[0].schedules : {}
}
