# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/modules/scheduler/variables.tf
# Description: Defines input variables for the Scheduler submodule.

variable "project_name" {
  description = "The name of the project."
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
  default     = {}
}

variable "schedule_cron_expression" {
  description = "Cron expression for the scheduler (e.g., 'cron(0 1 * * ? *)')."
  type        = string
  default     = "cron(0 1 * * ? *)"
}

variable "schedule_timezone" {
  description = "Timezone for the cron expression (e.g., 'UTC')."
  type        = string
  default     = "UTC"
}

variable "enable_scheduler" {
  description = "Set to false to disable the EventBridge Scheduler rule."
  type        = bool
  default     = true
}
