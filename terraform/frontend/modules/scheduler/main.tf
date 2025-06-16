# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/scheduler/main.tf
# Version: 0.0.9
# Purpose: Defines AWS EventBridge Scheduler resources for the frontend Scheduler submodule.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      # Not specifying version here, it should inherit constraints or use the one from root.
      # version = "~> 5.0" # Optionally, mirror the root or make it more flexible
    }
  }
}

# Local Variables
# ---------------
# Defines local names for IAM roles, policies, and the schedule itself,
# along with specific tags for these resources.
locals {
  // project_name is now var.project_name
  // common_tags is now var.common_tags
  // lambda_function_name comes from var.lambda_function_name

  scheduler_role_name  = "SchedulerInvoke-${var.lambda_function_name}-Role"
  scheduler_policy_name= "SchedulerInvoke-${var.lambda_function_name}-Policy"
  schedule_name        = "Daily-${var.lambda_function_name}-Trigger"
  schedule_description = "Triggers ${var.lambda_function_name} daily for ${var.project_name}"
  // schedule_cron_expression is now var.schedule_cron_expression
  // schedule_timezone is now var.schedule_timezone

  iam_tags = merge(var.common_tags, {
    Purpose = "SchedulerLambdaInvocation"
  })
  scheduler_tags = merge(var.common_tags, {
    Purpose = "DailyContentOrchestration"
  })
}

# IAM for Scheduler
# -----------------
# Creates the necessary IAM role and policy that EventBridge Scheduler
# will assume to get permissions to invoke the target Lambda function.

# Creates an IAM (Identity and Access Management) role that EventBridge Scheduler will assume
# to gain permissions to invoke the target Lambda function.
resource "aws_iam_role" "scheduler_invoke_content_orchestrator_lambda_role" {
  name = local.scheduler_role_name # Name of the IAM role in AWS.

  # Trust policy allowing EventBridge Scheduler service to assume this role.
  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow",
        Principal = {
          Service = "scheduler.amazonaws.com" # Grants trust to the EventBridge Scheduler service.
        },
        Action    = "sts:AssumeRole" # Allows the service to assume this role.
      }
    ]
  })

  tags = local.iam_tags
}

# Creates an IAM policy that grants permission to invoke the specific Content Orchestrator Lambda function.
# This policy will be attached to the scheduler's IAM role.
resource "aws_iam_policy" "scheduler_invoke_content_orchestrator_lambda_policy" {
  name        = local.scheduler_policy_name # Name of the IAM policy in AWS.
  description = "Allows EventBridge Scheduler to invoke the ${var.lambda_function_name} for ${var.project_name}"

  # Policy document granting invoke permission.
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow", # Specifies that this statement allows the action.
        Action   = "lambda:InvokeFunction", # The specific action allowed (invoking a Lambda function).
        Resource = var.lambda_function_arn # ARN of the target Lambda function.
      }
    ]
  })

  tags = local.iam_tags
}

# Attaches the IAM policy (granting Lambda invoke permission) to the IAM role
# that the EventBridge Scheduler will assume.
resource "aws_iam_role_policy_attachment" "scheduler_invoke_content_orchestrator_lambda_attach" {
  role       = aws_iam_role.scheduler_invoke_content_orchestrator_lambda_role.name # Name of the role to attach the policy to.
  policy_arn = aws_iam_policy.scheduler_invoke_content_orchestrator_lambda_policy.arn # ARN of the policy to attach.
}

# EventBridge Schedule Definition
# -------------------------------
# Defines the EventBridge Scheduler rule that triggers the specified Lambda function
# based on the provided cron expression and timezone.

# Creates an EventBridge Scheduler rule (schedule) that triggers the Content Orchestrator Lambda function
# on a daily basis.
resource "aws_scheduler_schedule" "daily_content_orchestrator_trigger" {
  name        = local.schedule_name        # Name of the schedule in AWS.
  description = local.schedule_description # A description for the schedule.
  group_name  = "default"                  # Schedules can be organized into groups; 'default' is used if not specified.

  schedule_expression          = var.schedule_cron_expression # Cron expression defining when the schedule runs.
  schedule_expression_timezone = var.schedule_timezone        # Timezone for the schedule expression.

  # Flexible time window configuration. 'OFF' means the schedule attempts to run at the exact time defined by cron.
  flexible_time_window {
    mode = "OFF"
  }

  # Target configuration: specifies the Lambda function to be invoked by this schedule.
  target {
    arn      = var.lambda_function_arn # ARN of the target Lambda function.
    role_arn = aws_iam_role.scheduler_invoke_content_orchestrator_lambda_role.arn # ARN of the IAM role that Scheduler assumes for invocation. [Ref: 23]

    # Optional: Input to pass to the Lambda function if needed.
    # input = jsonencode({
    #   "sourceDetail" = { "triggerName": local.schedule_name }
    # })
  }

  state = var.enable_scheduler ? "ENABLED" : "DISABLED" # Ensures the schedule is active upon creation. Can be "DISABLED".

  # Explicit dependencies to ensure IAM role and policy are fully configured before the schedule is created.
  depends_on = [
    aws_iam_role_policy_attachment.scheduler_invoke_content_orchestrator_lambda_attach
  ]
}