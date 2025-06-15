output "backend_lambda_execution_role_arn" {
  description = "ARN of the IAM role used by the backend Lambda functions."
  value       = module.backend_iam.lambda_execution_role_arn
}

output "backend_lambda_execution_role_name" {
  description = "Name of the IAM role used by the backend Lambda functions."
  value       = module.backend_iam.lambda_execution_role_name
}

output "backend_lambda_functions" {
  description = "Details of all deployed backend Lambda functions."
  value       = module.backend_lambda.lambda_function_details
  # This will output the entire map from the lambda module's "lambda_function_details"
}

output "backend_schedules" {
  description = "Details of all configured EventBridge schedules for the backend Lambdas."
  value       = module.backend_scheduler.schedule_details
  # This will output the entire map from the scheduler module's "schedule_details"
}

# Potentially more granular outputs if needed, for example, specific Lambda ARNs by name
# output "titan_llm_lambda_arn" {
#   description = "ARN of the Titan LLM Lambda function."
#   value       = try(module.backend_lambda.lambda_functions["titan-llm"].arn, null)
# }
# output "claude_llm_lambda_arn" {
#   description = "ARN of the Claude LLM Lambda function."
#   value       = try(module.backend_lambda.lambda_functions["claude-llm"].arn, null)
# }
# ... and so on for other specific lambdas if direct access to their ARNs is frequently needed.
# For now, the comprehensive map "backend_lambda_functions" should suffice.
