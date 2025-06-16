# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/scheduler/outputs.tf
# Version: 0.0.9
# Purpose: Declares outputs from the backend Scheduler submodule.

output "schedules" {
  description = "Map of created EventBridge schedules, keyed by their identifier from schedules_config."
  value = {
    for k, schedule_instance in module.individual_schedule : k => {
      # Values sourced from the scheduler_template module outputs (schedule_arn, schedule_name, iam_role_arn).
      arn          = schedule_instance.schedule_arn
      name         = schedule_instance.schedule_name
      iam_role_arn = schedule_instance.iam_role_arn
    }
  }
}

output "schedule_details" {
  description = "Detailed information about each created EventBridge schedule. This output exposes all outputs from the underlying scheduler_template instances."
  value       = module.individual_schedule
}
