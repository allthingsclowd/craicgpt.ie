# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/scheduler.tf
# Description: Sets up an AWS EventBridge Scheduler rule to trigger the ContentOrchestratorLambda
#              on a defined daily schedule (cron expression defined in locals). This includes creating
#              the necessary IAM role and policy for the scheduler to invoke the Lambda function.
#              Prerequisites: Content Orchestrator Lambda function ARN (from lambda.tf, via module output)
#                             and its name for constructing IAM resource names.
#              Validation: EventBridge Scheduler rule is 'Enabled' in the AWS console. The Lambda function
#                          is triggered according to the schedule (verify via Lambda logs in CloudWatch).
#                          IAM role and policy grant necessary invoke permissions.

# terraform/scheduler.tf

# Defines common values and configuration for AWS EventBridge Scheduler resources.
locals {
  project_name         = "CraicGPT.ie"
  scheduler_role_name  = "SchedulerInvoke-${module.content_orchestrator_lambda.lambda_function_name}-Role"
  scheduler_policy_name= "SchedulerInvoke-${module.content_orchestrator_lambda.lambda_function_name}-Policy"
  schedule_name        = "Daily-${module.content_orchestrator_lambda.lambda_function_name}-Trigger"
  schedule_description = "Triggers ${module.content_orchestrator_lambda.lambda_function_name} daily at 01:00 UTC for ${local.project_name}"

  # Cron expression for daily execution at 01:00 UTC.
  # Format: (minute hour day-of-month month day-of-week year). '?' denotes no specific value for day-of-week.
  schedule_cron_expression = "cron(0 1 * * ? *)" # [Ref: 23]
  schedule_timezone        = "UTC"               # Timezone for the cron expression. [Ref: 23]

  # Common tags to be applied to scheduler-related resources.
  common_tags = {
    Environment = "production"
    Project     = local.project_name
    ManagedBy   = "Terraform"
  }
  # Specific tags for IAM and Scheduler resources, merged with common tags.
  iam_tags = merge(local.common_tags, {
    Purpose = "SchedulerLambdaInvocation"
  })
  scheduler_tags = merge(local.common_tags, {
    Purpose = "DailyContentOrchestration"
  })
}

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
  description = "Allows EventBridge Scheduler to invoke the ${module.content_orchestrator_lambda.lambda_function_name} for ${local.project_name}"

  # Policy document granting invoke permission.
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow", # Specifies that this statement allows the action.
        Action   = "lambda:InvokeFunction", # The specific action allowed (invoking a Lambda function).
        Resource = module.content_orchestrator_lambda.lambda_function_arn # ARN of the target Lambda function.
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

# Creates an EventBridge Scheduler rule (schedule) that triggers the Content Orchestrator Lambda function
# on a daily basis.
resource "aws_scheduler_schedule" "daily_content_orchestrator_trigger" {
  name        = local.schedule_name        # Name of the schedule in AWS.
  description = local.schedule_description # A description for the schedule.
  group_name  = "default"                  # Schedules can be organized into groups; 'default' is used if not specified.

  schedule_expression          = local.schedule_cron_expression # Cron expression defining when the schedule runs.
  schedule_expression_timezone = local.schedule_timezone        # Timezone for the schedule expression.

  # Flexible time window configuration. 'OFF' means the schedule attempts to run at the exact time defined by cron.
  flexible_time_window {
    mode = "OFF"
  }

  # Target configuration: specifies the Lambda function to be invoked by this schedule.
  target {
    arn      = module.content_orchestrator_lambda.lambda_function_arn # ARN of the target Lambda function.
    role_arn = aws_iam_role.scheduler_invoke_content_orchestrator_lambda_role.arn # ARN of the IAM role that Scheduler assumes for invocation. [Ref: 23]

    # Optional: Input to pass to the Lambda function if needed.
    # input = jsonencode({
    #   "sourceDetail" = { "triggerName": local.schedule_name }
    # })
  }

  state = "ENABLED" # Ensures the schedule is active upon creation. Can be "DISABLED".

  # Explicit dependencies to ensure IAM role and policy are fully configured before the schedule is created.
  depends_on = [
    aws_iam_role_policy_attachment.scheduler_invoke_content_orchestrator_lambda_attach,
    module.content_orchestrator_lambda # Also depends on the Lambda module itself to ensure the Lambda function exists.
  ]

  tags = local.scheduler_tags
}