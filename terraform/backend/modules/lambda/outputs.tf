# Author: Graham Land
# Date: 16th June 2025
# File: terraform/backend/modules/lambda/outputs.tf
# Version: 0.0.9
# Purpose: Declares outputs from the backend Lambda submodule.

output "lambda_functions" {
  description = "Map of created Lambda functions, keyed by their identifier."
  value = {
    for k, lambda_instance in module.individual_lambda : k => {
      arn      = lambda_instance.lambda_function_arn # Corrected to match terraform-aws-modules/lambda output
      name     = lambda_instance.lambda_function_name # Corrected
      invoke_arn = lambda_instance.lambda_function_invoke_arn # Corrected
    }
  }
}

output "lambda_function_details" {
  description = "Detailed information about each created Lambda function. This output exposes all outputs from the underlying lambda_template instances."
  value = module.individual_lambda
}
