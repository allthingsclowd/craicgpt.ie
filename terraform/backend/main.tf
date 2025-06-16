# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/main.tf
# Version: 0.0.9
# Purpose: Defines the primary resources and module calls for the backend deployment.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.8.0"
}

provider "aws" {
  region = var.aws_region
}

locals {
  merged_common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Author      = "Graham Land"
    },
    var.common_tags
  )

  llm_lambdas_config = merge(
    var.enable_bedrock_lambdas ? {
      "titan-llm" = {
        handler          = "index.handler"
        runtime          = "python3.11"
        source_code_path = "titan_llm"
        description      = "Bedrock Titan LLM Invoker"
        bedrock_model_id = "amazon.titan-text-express-v1"
      },
      "claude-llm" = { # Bedrock Claude (e.g., Sonnet)
        handler          = "index.handler"
        runtime          = "python3.11"
        source_code_path = "claude_llm" # Placeholder, needs actual handler for Bedrock Claude
        description      = "Bedrock Claude LLM Invoker"
        bedrock_model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
      }
    } : {},
    var.enable_openai_lambdas && var.openai_api_key_secret_arn != null ? {
      "chatgpt-llm" = {
        handler                     = "index.handler" # Placeholder
        runtime                     = "python3.11"    # Placeholder
        source_code_path            = "chatgpt_llm"   # Placeholder
        description                 = "ChatGPT LLM Invoker"
        api_key_secret_var_name_ref = "openai_api_key_secret_arn"
      }
    } : {},
    var.enable_gemini_lambdas && var.gemini_api_key_secret_arn != null ? {
      "gemini-llm" = {
        handler                     = "index.handler" # Placeholder
        runtime                     = "python3.11"    # Placeholder
        source_code_path            = "gemini_llm"    # Placeholder
        description                 = "Gemini LLM Invoker"
        api_key_secret_var_name_ref = "gemini_api_key_secret_arn"
      }
    } : {}
    # Example for direct Anthropic (non-Bedrock) if var.anthropic_api_key_secret_arn is provided
    # var.enable_anthropic_direct_lambdas && var.anthropic_api_key_secret_arn != null ? {
    #   "anthropic-direct-llm" = {
    #     handler = "index.handler", runtime = "python3.11", source_code_path = "anthropic_direct_llm",
    #     description = "Anthropic Claude LLM Invoker (Direct API)",
    #     api_key_secret_var_name_ref = "anthropic_api_key_secret_arn"
    #   }
    # } : {},
  )

  image_gen_lambdas_config = merge(
    var.enable_bedrock_lambdas ? { # Bedrock Titan Image
      "titan-image" = {
        handler          = "index.handler" # Placeholder
        runtime          = "python3.11"    # Placeholder
        source_code_path = "titan_image"   # Placeholder
        description      = "Bedrock Titan Image Gen Invoker"
        bedrock_model_id = "amazon.titan-image-generator-v1"
      }
    } : {},
    var.enable_stability_lambdas ? { # Bedrock Stability Image
      "stability-image" = {
        handler          = "index.handler" # Placeholder
        runtime          = "python3.11"    # Placeholder
        source_code_path = "stability_image" # Placeholder
        description      = "Bedrock Stability AI Image Gen Invoker"
        bedrock_model_id = "stability.stable-diffusion-xl-v1"
        # If direct API for Stability was used, and stability_api_key_secret_arn passed to lambda module and mapped:
        # api_key_secret_var_name_ref = var.stability_api_key_secret_arn != null ? "stability_api_key_secret_arn" : null
      }
    } : {},
    var.enable_openai_lambdas && var.openai_api_key_secret_arn != null ? { # DALL-E via OpenAI
      "dalle-image" = {
        handler                     = "index.handler" # Placeholder
        runtime                     = "python3.11"    # Placeholder
        source_code_path            = "dalle_image"   # Placeholder
        description                 = "DALL-E Image Gen Invoker (OpenAI)"
        api_key_secret_var_name_ref = "openai_api_key_secret_arn"
      }
    } : {},
    var.enable_gemini_lambdas && var.gemini_api_key_secret_arn != null ? { # Gemini Image Gen (placeholder)
      "gemini-image" = {
        handler                     = "index.handler" # Placeholder
        runtime                     = "python3.11"    # Placeholder
        source_code_path            = "gemini_image"  # Placeholder
        description                 = "Gemini Image Gen Invoker"
        api_key_secret_var_name_ref = "gemini_api_key_secret_arn"
      }
    } : {}
  )
}

data "aws_caller_identity" "current" {}

# Remote state to get outputs from the frontend deployment
data "terraform_remote_state" "frontend" {
  backend = "s3"
  config = {
    bucket = var.frontend_terraform_state_bucket
    key    = var.frontend_terraform_state_key
    region = var.frontend_terraform_state_region
  }
}

# IAM Module for Backend Lambdas
module "backend_iam" {
  count = var.enable_backend_iam_module ? 1 : 0

  source = "./modules/iam"

  aws_region           = var.aws_region
  project_name         = var.project_name
  common_tags          = local.merged_common_tags
  s3_object_key_prefix_for_lambda_output = "dynamic_content/"
  bedrock_foundation_models_enabled = true
  additional_iam_policies = {}

  frontend_s3_bucket_arn = data.terraform_remote_state.frontend.outputs.s3_bucket_website_assets_arn

  api_key_secret_arns = compact([
    var.openai_api_key_secret_arn,
    var.gemini_api_key_secret_arn,
    var.stability_api_key_secret_arn, # Included for IAM policy if direct API is used
    var.anthropic_api_key_secret_arn  # Included for IAM policy if direct API is used
  ])
  # bedrock_foundation_models_enabled is true by default in the IAM module, granting Bedrock access.
}

# Lambda Functions Module
module "backend_lambda" {
  count = var.enable_backend_lambda_module && var.enable_backend_iam_module ? 1 : 0

  source = "./modules/lambda"

  project_name              = var.project_name
  aws_region                = var.aws_region
  common_tags               = local.merged_common_tags
  lambda_code_base_path     = var.lambda_code_root_path
  s3_output_object_key_prefix = "content/"
  s3_bucket_website_assets_name = data.terraform_remote_state.frontend.outputs.s3_bucket_name

  lambda_execution_role_arn = module.backend_iam[0].lambda_execution_role_arn
  s3_target_bucket_arn      = data.terraform_remote_state.frontend.outputs.s3_bucket_website_assets_arn

  # Pass through root API key ARN variables for the lambda module to map
  # These must be defined in backend_lambda/variables.tf and mapped in backend_lambda/main.tf's local.secret_arn_map
  openai_api_key_secret_arn    = var.openai_api_key_secret_arn
  gemini_api_key_secret_arn    = var.gemini_api_key_secret_arn
  stability_api_key_secret_arn = var.stability_api_key_secret_arn
  anthropic_api_key_secret_arn = var.anthropic_api_key_secret_arn

  llm_lambdas_config       = local.llm_lambdas_config
  image_gen_lambdas_config = local.image_gen_lambdas_config
}

# Scheduler Module
module "backend_scheduler" {
  count = var.enable_backend_scheduler_module && var.enable_backend_lambda_module && var.enable_backend_iam_module ? 1 : 0

  source = "./modules/scheduler"

  project_name         = var.project_name
  aws_region           = var.aws_region
  common_tags          = local.merged_common_tags
  lambda_functions_map = module.backend_lambda[0].lambda_functions # Output from the lambda module

  schedules_config = merge(
    { # Schedules for LLM Lambdas
      for k, cfg in local.llm_lambdas_config : k => {
        lambda_identifier = k # Uses the key from llm_lambdas_config (e.g., "titan-llm")
        description       = "Daily 6 AM trigger for ${lookup(cfg, "description", "LLM Lambda")}"
        # enabled field in scheduler module defaults to true, cron expression also defaults
      } if( # Only create schedule if corresponding Lambda is enabled via root variable
          (contains(["titan-llm", "claude-llm"], k) && var.enable_bedrock_lambdas) ||
          (k == "chatgpt-llm" && var.enable_openai_lambdas && var.openai_api_key_secret_arn != null) ||
          (k == "gemini-llm" && var.enable_gemini_lambdas && var.gemini_api_key_secret_arn != null)
          # Add similar condition for direct anthropic if that config is added:
          # (k == "anthropic-direct-llm" && var.enable_anthropic_direct_lambdas && var.anthropic_api_key_secret_arn != null)
      )
    },
    { # Schedules for Image Gen Lambdas
      for k, cfg in local.image_gen_lambdas_config : k => {
        lambda_identifier = k
        description       = "Daily 6 AM trigger for ${lookup(cfg, "description", "Image Gen Lambda")}"
      } if(
          (k == "titan-image" && var.enable_bedrock_lambdas) ||
          (k == "stability-image" && var.enable_stability_lambdas) || # Assumes stability-image is part of bedrock or direct with key
          (k == "dalle-image" && var.enable_openai_lambdas && var.openai_api_key_secret_arn != null) ||
          (k == "gemini-image" && var.enable_gemini_lambdas && var.gemini_api_key_secret_arn != null)
      )
    }
  )
}
