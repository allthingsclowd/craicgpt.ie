data "aws_caller_identity" "current" {}

resource "aws_iam_role" "backend_lambda_execution_role" {
  name = "${var.project_name}-backend-lambda-role"

  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Action    = "sts:AssumeRole",
        Effect    = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-backend-lambda-role"
  })
}

# Inline policy for essential permissions
resource "aws_iam_role_policy" "lambda_essential_permissions" {
  name = "${var.project_name}-lambda-essential-policy"
  role = aws_iam_role.backend_lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow",
        Action   = ["s3:PutObject", "s3:PutObjectAcl"], # Added PutObjectAcl for potential public read if needed later
        Resource = "${var.frontend_s3_bucket_arn}/${var.s3_object_key_prefix_for_lambda_output}*"
      }
    ]
  })
}

# Conditional policy for Bedrock
resource "aws_iam_role_policy" "lambda_bedrock_permissions" {
  count = var.bedrock_foundation_models_enabled ? 1 : 0

  name = "${var.project_name}-lambda-bedrock-policy"
  role = aws_iam_role.backend_lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = "bedrock:InvokeModel",
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/*" # Access to all foundation models
      }
    ]
  })
}

# Conditional policy for Secrets Manager
resource "aws_iam_role_policy" "lambda_secrets_manager_permissions" {
  count = length(var.api_key_secret_arns) > 0 ? 1 : 0

  name = "${var.project_name}-lambda-secrets-policy"
  role = aws_iam_role.backend_lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = "secretsmanager:GetSecretValue",
        Resource = var.api_key_secret_arns
      }
    ]
  })
}

# Attach additional policies
resource "aws_iam_role_policy" "additional_policies" {
  for_each = var.additional_iam_policies

  name = "${var.project_name}-lambda-additional-policy-${each.key}"
  role = aws_iam_role.backend_lambda_execution_role.id
  policy = each.value
}
