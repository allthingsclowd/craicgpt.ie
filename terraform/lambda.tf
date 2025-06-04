# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/lambda.tf
# Description: Defines the 'ContentOrchestratorLambda' using the terraform-aws-modules/lambda/aws module.
#              This includes its IAM execution role, necessary permissions (CloudWatch Logs, S3 Put, Secrets Manager Get),
#              and environment variables for accessing other services.
#              Prerequisites: S3 bucket ARN (from s3.tf, via aws_s3_bucket.website_assets.bucket/arn),
#                             API key ARNs for LLM and Image Gen (from variables.tf, sourced from AWS Secrets Manager).
#                             Lambda source code located at locals.lambda_source_path.
#              Validation: Lambda function created in AWS console with correct runtime, handler, and environment variables.
#                          IAM role for Lambda exists with attached policies granting specified permissions.
#                          Lambda function logs appear in CloudWatch Logs.

# terraform/lambda.tf

# Defines common values and configuration for the Lambda module.
locals {
  project_name      = "CraicGPT.ie"
  lambda_function_name = "ContentOrchestratorLambda"
  lambda_description   = "Orchestrates daily content generation for ${local.project_name}"
  lambda_handler       = "index.handler" # Assumes the Lambda entry point is 'index.js' and it exports a function named 'handler'.
  lambda_runtime       = "nodejs18.x"    # Specifies the Node.js 18.x runtime environment. [Ref: 18]
  lambda_source_path   = "../lambda_code/content_orchestrator" # Path to the Lambda function's source code.

  # Common tags to be applied to all resources created by this module instance.
  common_tags = {
    Environment = "production"
    Project     = local.project_name
    ManagedBy   = "Terraform"
  }
  # Specific tags for the Lambda function, merged with common tags.
  lambda_tags = merge(local.common_tags, {
    Name         = local.lambda_function_name
    Orchestrates = "DailyContentGeneration" # More descriptive tag
  })
}

# Provisions the AWS Lambda function responsible for orchestrating daily content generation.
# This module, from terraform-aws-modules/lambda/aws, simplifies the creation and configuration
# of the Lambda function, its IAM role, and necessary permissions.
module "content_orchestrator_lambda" {
  source = "terraform-aws-modules/lambda/aws"
  # It's recommended to pin to a specific version of the module for stability.
  # version = "~> 7.0" # Example: Check module documentation for the latest appropriate version.

  function_name = local.lambda_function_name # The name of the Lambda function in AWS.
  description   = local.lambda_description   # A description for the Lambda function.
  handler       = local.lambda_handler
  runtime       = local.lambda_runtime

  # Specifies the location of the Lambda function's source code.
  # If 'source_path' points to a directory containing a 'package.json' (for Node.js runtimes),
  # the module may attempt to build the package by running 'npm install'.
  # Alternatively, it can be a path to a pre-built ZIP file.
  source_path = local.lambda_source_path # Ensure this path is correct relative to the Terraform execution directory.

  # Environment variables made available to the Lambda function at runtime. [Ref: 18]
  environment_variables = {
    S3_BUCKET_NAME              = aws_s3_bucket.website_assets.bucket # Name of the S3 bucket for storing generated content.
    LLM_API_KEY_SECRET_ARN      = var.llm_api_key_secret_arn          # ARN of the Secrets Manager secret for the LLM API key.
    IMAGEGEN_API_KEY_SECRET_ARN = var.image_gen_api_key_secret_arn    # ARN of the Secrets Manager secret for the Image Generator API key.
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
      resources = ["${aws_s3_bucket.website_assets.arn}/content/*"] 
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
