# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/scheduler_template/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the backend Scheduler Template submodule.

variable "project_name" {
  description = "The name of the project."
  type        = string
}

variable "schedule_description" {
  description = "Description for the EventBridge Schedule rule."
  type        = string
}

variable "lambda_function_name" {
  description = "Name of the Lambda function to be triggered by the scheduler."
  type        = string
}

variable "lambda_function_arn" {
  description = "ARN of the Lambda function to be triggered by the scheduler."
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
}

variable "tags" {
  description = "A map of tags to assign to the scheduler rule."
  type        = map(string)
}

variable "schedule_cron_expression" {
  description = "Cron expression for the scheduler (e.g., 'cron(0 1 * * ? *)')."
  type        = string
}

variable "schedule_timezone" {
  description = "Timezone for the cron expression (e.g., 'UTC')."
  type        = string
}

variable "enable_scheduler" {
  description = "Set to false to disable the EventBridge Scheduler rule."
  type        = bool
}
