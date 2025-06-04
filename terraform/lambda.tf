# /terraform/lambda.tf

module "content_orchestrator_lambda" {
  source = "terraform-aws-modules/lambda/aws"
  # Ensure you are using a version of the module that supports the features you need.
  # Check the module's documentation for the latest version. Example:
  # version = "~> 7.0" 

  function_name = "ContentOrchestratorLambda"
  description   = "Orchestrates daily content generation for CraicGPT.ie"
  handler       = "index.handler" # Assuming the entry point is index.js and exports 'handler'
  runtime       = "nodejs18.x"    # As requested [18]

  # source_path can be a local directory containing Lambda code and package.json,
  # or a path to a pre-built ZIP file.
  # If a directory with package.json for nodejs runtime, the module can attempt to build it.
  source_path = "../lambda_code/content_orchestrator" # Update with actual path to Lambda code

  # Environment variables passed to the Lambda function [18]
  environment_variables = {
    S3_BUCKET_NAME                = aws_s3_bucket.website_assets.bucket
    LLM_API_KEY_SECRET_ARN        = var.llm_api_key_secret_arn
    IMAGEGEN_API_KEY_SECRET_ARN   = var.image_gen_api_key_secret_arn
    # Add other necessary environment variables, e.g., API endpoints if they are configurable
    # LLM_PROVIDER_TYPE             = "GEMINI" # Example
    # IMAGE_GEN_PROVIDER_TYPE     = "OPENAI" # Example
  }

  # IAM policy statements attached to the Lambda execution role [19]
  # The module creates the role and attaches these statements.
  attach_policy_statements = true
  policy_statements = {
    CloudWatchLogs = {
      effect    = "Allow"
      actions   =
      resources = ["arn:aws:logs:*:*:*"] # Standard logging permissions
    },
    S3PutContent = {
      effect    = "Allow"
      actions   = ["s3:PutObject"]
      # Scoped down to the /content/ path within the specific bucket
      resources = ["${aws_s3_bucket.website_assets.arn}/content/*"] 
    },
    SecretsManagerGetLLMKey = {
      effect    = "Allow"
      actions   =
      # Scoped down to the specific LLM API key secret ARN
      resources = [var.llm_api_key_secret_arn]
    },
    SecretsManagerGetImageGenKey = {
      effect    = "Allow"
      actions   =
      # Scoped down to the specific ImageGen API key secret ARN
      resources = [var.image_gen_api_key_secret_arn]
    }
    # Add other permissions if the orchestrator invokes other Lambdas, etc.
    # e.g., InvokeLLMHandler = {... actions = ["lambda:InvokeFunction"]... }
  }

  # Optional: If Lambda needs VPC access (e.g., to access resources in a VPC)
  # vpc_subnet_ids         = var.lambda_subnet_ids
  # vpc_security_group_ids = var.lambda_security_group_ids
  # attach_network_policy  = true # If VPC settings are provided

  tags = {
    Environment = "production"
    Project     = "CraicGPT.ie"
    Orchestrates = "DailyContent"
  }
}
