output "lambda_execution_role_arn" {
  description = "ARN of the IAM role for Lambda execution."
  value       = aws_iam_role.backend_lambda_execution_role.arn
}

output "lambda_execution_role_name" {
  description = "Name of the IAM role for Lambda execution."
  value       = aws_iam_role.backend_lambda_execution_role.name
}
