# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/main.tf
# Version: 0.0.9
# Purpose: Defines the main infrastructure resources for the frontend root module.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # Specify a version constraint
    }
  }
  required_version = ">= 1.8.0" # Or your target minimum version, e.g., ">= 1.12.1"
}

provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "us_east_1_acm"
  region = "us-east-1" # ACM certificates for CloudFront must be in us-east-1
}

data "aws_caller_identity" "current" {}

# Data source to get the Route 53 hosted zone for your domain
data "aws_route53_zone" "primary" {
  count = var.enable_cloudfront ? 1 : 0 # Only fetch if CloudFront is enabled
  name  = var.domain_name # e.g., "craicgpt.ie"
}

# ACM Module for SSL/TLS Certificate
module "acm" {
  source = "./modules/acm"
  count  = var.enable_acm ? 1 : 0

  project_name    = var.project_name
  domain_name     = var.domain_name # e.g., "craicgpt.ie"
  subject_alternative_names_list = var.cloudfront_aliases # Pass all required aliases to the ACM module
  common_tags     = local.merged_common_tags
  # The acm module's internal provider reference will use 'aws.us_east_1_acm' via var.aws_provider_alias_us_east_1
  # This ensures the module knows which provider configuration to pick up if multiple are passed or available.
  # However, the `providers` meta-argument below is the more direct way to assign it.


  providers = {
    aws = aws.us_east_1_acm # Pass the aliased provider configuration to be used as the default 'aws' provider within this module
  }
}

# S3 Module for Website Assets
module "s3" {
  source = "./modules/s3"
  count  = var.enable_s3 ? 1 : 0

  bucket_name       = var.s3_bucket_name_override == "" ? "${var.project_name}-website-assets" : var.s3_bucket_name_override
  common_tags       = local.merged_common_tags
  enable_versioning = var.s3_enable_versioning
  index_document    = var.s3_website_index_document
  error_document    = var.s3_website_error_document
}

# CloudFront Module for Content Delivery
module "cloudfront" {
  source = "./modules/cloudfront"
  count  = var.enable_cloudfront ? 1 : 0

  project_name                            = var.project_name
  s3_bucket_website_assets_id             = module.s3[0].bucket_id
  s3_bucket_website_assets_arn            = module.s3[0].bucket_arn
  s3_bucket_website_assets_regional_domain_name = module.s3[0].bucket_regional_domain_name
  acm_certificate_validation_arn          = module.acm[0].certificate_validation_arn
  cloudfront_aliases                      = var.cloudfront_aliases
  common_tags                             = local.merged_common_tags
  aws_account_id                          = data.aws_caller_identity.current.account_id
  default_root_object                     = var.cloudfront_default_root_object
  price_class                             = var.cloudfront_price_class
  enable_distribution                     = var.enable_cloudfront
  # root var.enable_cloudfront controls if the module is instantiated via count.
}

# DNS Records for CloudFront Distribution
resource "aws_route53_record" "cloudfront_aliases" {
  count = var.enable_cloudfront ? length(var.cloudfront_aliases) : 0

  zone_id = data.aws_route53_zone.primary[0].zone_id
  name    = var.cloudfront_aliases[count.index]
  type    = "A" # Use A record for Alias to CloudFront

  alias {
    name                   = module.cloudfront[0].distribution_domain_name
    zone_id                = module.cloudfront[0].distribution_hosted_zone_id # CloudFront's hosted zone ID for Alias records
    evaluate_target_health = false
  }

  # Ensure CloudFront distribution is created before DNS records
  depends_on = [module.cloudfront]
}

# Frontend Upload Module for S3 content
module "frontend_upload" {
  source = "./modules/frontend-upload"
  count  = var.enable_frontend_upload && var.enable_s3 ? 1 : 0 # Depends on S3 being enabled

  s3_bucket_id       = module.s3[0].bucket_id
  frontend_directory = var.s3_frontend_content_path # Use existing variable for path
  common_tags        = local.merged_common_tags
  enable_upload      = var.enable_frontend_upload # Internal enable flag, root control is via count
}

# Lambda Module for Content Orchestration
module "lambda" {
  source = "./modules/lambda"
  count  = var.enable_lambda ? 1 : 0

  project_name                  = var.project_name
  s3_bucket_website_assets_name = module.s3[0].bucket_name
  s3_bucket_website_assets_arn  = module.s3[0].bucket_arn
  llm_api_key_secret_arn        = var.llm_api_key_secret_arn
  image_gen_api_key_secret_arn  = var.image_gen_api_key_secret_arn
  common_tags                   = local.merged_common_tags
  lambda_source_path_override   = var.lambda_source_path_override
  lambda_handler_override       = var.lambda_handler_override
  lambda_runtime_override       = var.lambda_runtime_override
  lambda_function_name_override = var.lambda_function_name_override
  enable_lambda                 = var.enable_lambda
  # root var.enable_lambda controls if the module is instantiated via count.
}

# Scheduler Module for Daily Lambda Trigger
module "scheduler" {
  source = "./modules/scheduler"
  count  = var.enable_scheduler ? 1 : 0

  project_name            = var.project_name
  lambda_function_name    = module.lambda[0].function_name
  lambda_function_arn     = module.lambda[0].function_arn
  common_tags             = local.merged_common_tags
  schedule_cron_expression = var.scheduler_cron_expression
  schedule_timezone       = var.scheduler_timezone
  enable_scheduler        = var.enable_scheduler
  # root var.enable_scheduler controls if the module is instantiated via count.
}
