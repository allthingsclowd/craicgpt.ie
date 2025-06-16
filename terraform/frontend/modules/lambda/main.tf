# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/lambda/main.tf
# Version: 0.0.9
# Purpose: Defines AWS Lambda function and related IAM resources for the frontend Lambda submodule.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      # Not specifying version here, it should inherit constraints or use the one from root.
      # version = "~> 5.0" # Optionally, mirror the root or make it more flexible
    }
  }
}

locals {
  // project_name is now var.project_name
  // common_tags is now var.common_tags

  lambda_function_name = var.lambda_function_name_override
  lambda_description   = "Orchestrates daily content generation for ${var.project_name}"
  lambda_handler       = var.lambda_handler_override
  lambda_runtime       = var.lambda_runtime_override
  lambda_source_path   = var.lambda_source_path_override

  lambda_tags = merge(var.common_tags, {
    Name         = local.lambda_function_name
    Orchestrates = "DailyContentGeneration"
  })
}

# Provisions the AWS Lambda function responsible for orchestrating daily content generation.
# This module, from terraform-aws-modules/lambda/aws, simplifies the creation and configuration
# of the Lambda function, its IAM role, and necessary permissions.
module "content_orchestrator_lambda" {
  source = "terraform-aws-modules/lambda/aws"
  # It's recommended to pin to a specific version of the module for stability.
  # version = "~> 7.0" # Example: Check module documentation for the latest appropriate version.

  create_function = var.enable_lambda

  function_name = local.lambda_function_name
  description   = local.lambda_description
  handler       = local.lambda_handler
  runtime       = local.lambda_runtime
  source_path   = local.lambda_source_path

  # Environment variables made available to the Lambda function at runtime. [Ref: 18]
  environment_variables = {
    S3_BUCKET_NAME              = var.s3_bucket_website_assets_name
    LLM_API_KEY_SECRET_ARN      = var.llm_api_key_secret_arn
    IMAGEGEN_API_KEY_SECRET_ARN = var.image_gen_api_key_secret_arn
    # Example: Add other necessary environment variables, such as API endpoints or provider types if configurable.
    # LLM_PROVIDER_TYPE           = "GEMINI"
    # IMAGE_GEN_PROVIDER_TYPE   = "OPENAI"
  }

  # Defines IAM policy statements that will be attached to the Lambda function's execution role.
  # The module automatically creates the IAM role and attaches these policy statements. [Ref: 19]
  attach_policy_statements = true # Instructs the module to manage policy attachments.
  policy_statements = {
    # Permissions for CloudWatch Logs, allowing the Lambda function to write logs.
    CloudWatchLogs = {
      effect    = "Allow"
      actions   = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      resources = ["arn:aws:logs:*:*:*"] # Allows logging to any log group (standard practice).
    },
    # Permissions to put objects into the specified S3 bucket, under the "/content/" path.
    S3PutContent = {
      effect    = "Allow"
      actions   = ["s3:PutObject"]
      # Scoped down to the '/content/' prefix within the specific S3 bucket used for website assets.
      resources = ["${var.s3_bucket_website_assets_arn}/content/*"]
    },
    # Permissions to retrieve the LLM API key from AWS Secrets Manager.
    SecretsManagerGetLLMKey = {
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      # Scoped down to the specific ARN of the LLM API key secret.
      resources = [var.llm_api_key_secret_arn]
    },
    # Permissions to retrieve the Image Generator API key from AWS Secrets Manager.
    SecretsManagerGetImageGenKey = {
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      # Scoped down to the specific ARN of the Image Generator API key secret.
      resources = [var.image_gen_api_key_secret_arn]
    }
    # Example: Add other permissions if the orchestrator needs to invoke other Lambda functions,
    # interact with other AWS services, etc.
    # InvokeLLMHandler = {
    #   effect    = "Allow"
    #   actions   = ["lambda:InvokeFunction"]
    #   resources = [module.llm_handler_lambda.lambda_function_arn] # Assuming another Lambda module
    # }
  }

  # Optional: VPC configuration if the Lambda function needs to access resources within a VPC
  # (e.g., RDS databases, ElastiCache clusters).
  # vpc_subnet_ids         = var.lambda_subnet_ids
  # vpc_security_group_ids = var.lambda_security_group_ids
  # attach_network_policy  = true # Required if VPC settings are provided.

  tags = local.lambda_tags # Applies the defined tags to the Lambda function and related resources.
}
