# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/scheduler/outputs.tf
# Version: 0.0.9
# Purpose: Declares outputs for the frontend scheduler submodule.

output "schedule_name" {
  description = "The name of the EventBridge Scheduler rule."
  value       = aws_scheduler_schedule.daily_content_orchestrator_trigger.name
}

output "schedule_arn" {
  description = "The ARN of the EventBridge Scheduler rule."
  value       = aws_scheduler_schedule.daily_content_orchestrator_trigger.arn
}

output "iam_role_name" {
  description = "The name of the IAM role created for the scheduler."
  value       = aws_iam_role.scheduler_invoke_content_orchestrator_lambda_role.name
}

output "iam_role_arn" {
  description = "The ARN of the IAM role created for the scheduler."
  value       = aws_iam_role.scheduler_invoke_content_orchestrator_lambda_role.arn
}
