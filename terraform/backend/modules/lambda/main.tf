# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/lambda/main.tf
# Version: 0.0.9
# Purpose: Defines AWS Lambda functions for the backend Lambda submodule.

locals {
  all_lambdas = merge(
    var.llm_lambdas_config,
    var.image_gen_lambdas_config
  )

  # Helper to get actual secret ARN from the variable name string defined in this module's variables.tf
  secret_arn_map = {
    "openai_api_key_secret_arn"    = var.openai_api_key_secret_arn,
    "gemini_api_key_secret_arn"    = var.gemini_api_key_secret_arn,
    "stability_api_key_secret_arn" = var.stability_api_key_secret_arn, # New
    "anthropic_api_key_secret_arn" = var.anthropic_api_key_secret_arn  # New
    # Add other mappings here if more module-level secret ARN variables are added
  }
}

module "individual_lambda" {
  for_each = local.all_lambdas

  source = "../lambda_template" # Path to the refactored lambda_template module

  project_name                  = var.project_name
  # aws_region is not directly used by lambda_template, but good to pass if it were needed for some internal logic
  # lambda_template gets region from data source if needed for role creation, but here we pass existing role.
  lambda_function_name_override = "${var.project_name}-${each.key}-lambda"
  lambda_description            = each.value.description
  lambda_handler_override       = each.value.handler
  lambda_runtime_override       = each.value.runtime
  lambda_source_path_override   = "${var.lambda_code_base_path}/${each.value.source_code_path}"

  # Performance settings
  lambda_timeout     = each.value.timeout_seconds
  lambda_memory_size = each.value.memory_size_mb

  # IAM Role - Pass the externally created role ARN to lambda_template
  existing_lambda_role_arn = var.lambda_execution_role_arn

  # The following policy-related variables for lambda_template will NOT be used by it
  # for policy creation if existing_lambda_role_arn is provided (which is the case here).
  # These are passed for completeness or if lambda_template might use them for non-policy purposes.
  s3_target_bucket_arn = var.s3_target_bucket_arn
  s3_object_key_prefix = "${var.s3_output_object_key_prefix}${each.key}/" # For environment variables

  # These policy-related inputs for lambda_template are effectively ignored by it when existing_lambda_role_arn is set.
  # The IAM role (var.lambda_execution_role_arn) is assumed to already have these permissions if needed.
  secret_arns_to_access = compact([
    each.value.api_key_secret_var_name_ref != null ? local.secret_arn_map[each.value.api_key_secret_var_name_ref] : null
  ])

  bedrock_model_arns_to_access = compact(
    each.value.bedrock_model_id == "*" ? ["arn:aws:bedrock:${var.aws_region}::foundation-model/*"] :
    each.value.bedrock_model_id != null ? ["arn:aws:bedrock:${var.aws_region}::foundation-model/${each.value.bedrock_model_id}"] :
    null # This structure ensures a list or null is passed to compact.
  )

  # Environment variables
  lambda_environment_variables = merge(
    {
      S3_OUTPUT_BUCKET_ARN = var.s3_target_bucket_arn # Lambda code might need bucket ARN
      S3_OUTPUT_PREFIX     = "${var.s3_output_object_key_prefix}${each.key}/"
      AWS_REGION           = var.aws_region # Common useful env var
      # Add other common env vars for all backend lambdas here
    },
    each.value.environment_variables, # Lambda-specific env vars from config
    (each.value.api_key_secret_var_name_ref != null && local.secret_arn_map[each.value.api_key_secret_var_name_ref] != null ? {
      API_KEY_SECRET_ARN = local.secret_arn_map[each.value.api_key_secret_var_name_ref]
    } : {}),
    (each.value.bedrock_model_id != null ? {
      BEDROCK_MODEL_ID = each.value.bedrock_model_id
    } : {})
  )

  common_tags = var.common_tags # Pass common_tags from this module's variables
  # Tags specific to this lambda instance, merged with common_tags by lambda_template
}
