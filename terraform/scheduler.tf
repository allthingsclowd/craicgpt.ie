# /terraform/scheduler.tf

# IAM Role for EventBridge Scheduler to invoke the ContentOrchestratorLambda
resource "aws_iam_role" "scheduler_invoke_content_orchestrator_lambda_role" {
  name = "SchedulerInvokeContentOrchestratorLambdaRole"

  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement =
        }
      }
    ]
  })

  tags = {
    Environment = "production"
    Project     = "CraicGPT.ie"
  }
}

resource "aws_iam_policy" "scheduler_invoke_content_orchestrator_lambda_policy" {
  name        = "SchedulerInvokeContentOrchestratorLambdaPolicy"
  description = "Allows EventBridge Scheduler to invoke the ContentOrchestratorLambda"

  policy = jsonencode({
    Version   = "2012-10-17",
    Statement =
        Resource = module.content_orchestrator_lambda.lambda_function_arn 
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_invoke_content_orchestrator_lambda_attach" {
  role       = aws_iam_role.scheduler_invoke_content_orchestrator_lambda_role.name
  policy_arn = aws_iam_policy.scheduler_invoke_content_orchestrator_lambda_policy.arn
}

# EventBridge Scheduler Rule
resource "aws_scheduler_schedule" "daily_content_orchestrator_trigger" {
  name        = "DailyContentOrchestratorTrigger"
  description = "Triggers ContentOrchestratorLambda daily at 01:00 UTC"
  group_name  = "default" # Can be a custom group name

  # Cron expression for daily at 01:00 UTC: (minute hour day-of-month month day-of-week year)
  schedule_expression          = "cron(0 1 * *? *)" # [23]
  schedule_expression_timezone = "UTC"               # Explicitly set timezone [23]

  flexible_time_window {
    mode = "OFF" # For precise cron-based scheduling
  }

  target {
    arn      = module.content_orchestrator_lambda.lambda_function_arn # ARN of the target Lambda function
    role_arn = aws_iam_role.scheduler_invoke_content_orchestrator_lambda_role.arn # ARN of the IAM role for invocation [23]

    # Optional: Input to pass to the Lambda function if needed
    # input = jsonencode({
    #   "source"      = "aws.scheduler",
    #   "triggerTime" = formatdate("YYYY-MM-DD'T'hh:mm:ssZ", timestamp())
    # })
  }

  state = "ENABLED" # Ensure the schedule is active

  depends_on = [
    aws_iam_role_policy_attachment.scheduler_invoke_content_orchestrator_lambda_attach,
    module.content_orchestrator_lambda
  ]

  tags = {
    Environment = "production"
    Project     = "CraicGPT.ie"
  }
}