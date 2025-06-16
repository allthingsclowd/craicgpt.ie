# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/lambda_template/main.tf
# Version: 0.0.9
# Purpose: Defines a generic AWS Lambda function template for the backend Lambda Template submodule.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      # Not specifying version here, it should inherit constraints or use the one from root.
    }
  }
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {} # Useful for constructing ARNs if needed, e.g. for default S3 bucket policies

locals {
  lambda_function_name = var.lambda_function_name_override
  lambda_handler       = var.lambda_handler_override
  lambda_runtime       = var.lambda_runtime_override
  lambda_source_path   = var.lambda_source_path_override

  lambda_tags = merge(var.common_tags, {
    Name = local.lambda_function_name
  })

  # Dynamically construct policy statements for when this module creates the IAM role.
  # These policies will only be attached if var.existing_lambda_role_arn is null.
  merged_policy_statements = {
    CloudWatchLogs = {
      effect    = "Allow"
      actions   = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      resources = ["arn:aws:logs:*:*:*"]
    },
    # S3PutObject policy - only if s3_target_bucket_arn is provided AND role is created by module
    S3PutObject = var.s3_target_bucket_arn != null ? [{
      effect    = "Allow"
      actions   = ["s3:PutObject"] # Consider if s3:PutObjectAcl is needed
      resources = ["${var.s3_target_bucket_arn}/${var.s3_object_key_prefix}*"]
    }] : [], # The terraform-aws-modules/lambda/aws module expects a list for policy statements map values
    # SecretsManagerAccess policy - only if secret_arns_to_access is not empty AND role is created by module
    SecretsManagerAccess = length(var.secret_arns_to_access) > 0 ? [{
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = var.secret_arns_to_access
    }] : [],
    # BedrockInvokeAccess policy - only if bedrock_model_arns_to_access is not empty AND role is created by module
    BedrockInvokeAccess = length(var.bedrock_model_arns_to_access) > 0 ? [{
      effect  = "Allow"
      actions = ["bedrock:InvokeModel"]
      resources = (
        length(var.bedrock_model_arns_to_access) == 1 && var.bedrock_model_arns_to_access[0] == "*"
        ? ["arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/*"]
        : var.bedrock_model_arns_to_access
      )
    }] : []
  }

  # Cleaned merged_policy_statements: remove keys with empty lists
  # The terraform-aws-modules/lambda/aws module expects the policy_statements map values to be lists of statement blocks.
  # An empty list for a policy key is acceptable and means "no statements for this policy key".
  # However, if a key itself should be absent if no statements, further filtering is needed.
  # For now, the structure of merged_policy_statements produces lists (possibly empty) for each key,
  # which is compatible with how policy_statements is processed if it's a map of lists.
  # The AWS Lambda module source code shows `jsondecode(statement)` for each statement in the list.
  # Let's adjust merged_policy_statements to be a simple map of statements, and rely on the module's internal handling.
  # The `terraform-aws-modules/lambda/aws` documentation for `policy_statements` says:
  # "A map of IAM policy [statements](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document#statement) to attach to the Lambda role."
  # This implies it should be a map of statement blocks, not a map of lists of statement blocks.
  # Reverting the structure of merged_policy_statements to direct map of objects, and using null to omit.

  final_policy_statements = var.existing_lambda_role_arn == null ? {
    CloudWatchLogs = {
      effect    = "Allow"
      actions   = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      resources = ["arn:aws:logs:*:*:*"]
    }
    S3PutObject = var.s3_target_bucket_arn != null ? {
      effect    = "Allow"
      actions   = ["s3:PutObject"]
      resources = ["${var.s3_target_bucket_arn}/${var.s3_object_key_prefix}*"]
    } : null # This will be filtered out by merge if null
    SecretsManagerAccess = length(var.secret_arns_to_access) > 0 ? {
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = var.secret_arns_to_access
    } : null
    BedrockInvokeAccess = length(var.bedrock_model_arns_to_access) > 0 ? {
      effect  = "Allow"
      actions = ["bedrock:InvokeModel"]
      resources = (
        length(var.bedrock_model_arns_to_access) == 1 && var.bedrock_model_arns_to_access[0] == "*"
        ? ["arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/*"]
        : var.bedrock_model_arns_to_access
      )
    } : null
  } : {} // Empty map if role is existing

  # Filter out null policies for the final map
  filtered_final_policy_statements = {
    for k, v in local.final_policy_statements : k => v if v != null
  }
}

module "generic_lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.2"

  create_function = var.enable_lambda

  function_name = local.lambda_function_name
  description   = var.lambda_description
  handler       = local.lambda_handler
  runtime       = local.lambda_runtime
  source_path   = local.lambda_source_path

  # Role handling
  create_role = (var.existing_lambda_role_arn == null)
  lambda_role = var.existing_lambda_role_arn

  # Performance
  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory_size

  environment_variables = var.lambda_environment_variables

  # IAM Policies - only attach if role is created by this module
  attach_policy_statements = (var.existing_lambda_role_arn == null) # Attach statements only if we create the role
  policy_statements        = local.filtered_final_policy_statements # Use the filtered map

  tags = local.lambda_tags
}
