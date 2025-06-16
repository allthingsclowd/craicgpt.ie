# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/scheduler/variables.tf
# Version: 0.0.9
# Purpose: Defines input variables for the backend Scheduler submodule.

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

variable "lambda_functions_map" {
  description = "A map of Lambda function details, where keys are identifiers (e.g., 'titan-llm') and values are objects containing at least 'arn' and 'name'."
  type = map(object({
    arn  = string
    name = string
    # Potentially other details from the lambda module's output if needed
  }))
  default = {}
}

variable "schedules_config" {
  description = "Configuration map for EventBridge schedules. Key is a unique schedule identifier."
  type = map(object({
    lambda_identifier   = string # Key to look up in lambda_functions_map
    schedule_expression = optional(string, "cron(0 6 * * ? *)") # Default: 6 AM daily
    timezone            = optional(string, "UTC")
    description         = optional(string, "Daily trigger for Lambda function")
    enabled             = optional(bool, true)
  }))
  default = {}
}
