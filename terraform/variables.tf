# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/variables.tf
# Description: Declares input variables used throughout the Terraform configuration. These variables
#              allow for customization of the deployment, such as specifying the AWS region,
#              domain names, and ARNs for sensitive data like API keys stored in Secrets Manager.
#              Prerequisites: None (this file defines inputs; values are provided during 'terraform apply'
#                             or via .tfvars files).
#              Validation: When running 'terraform plan' or 'terraform apply', Terraform will prompt
#                          for any undefined variables that do not have default values. Default values
#                          are used correctly if no other value is provided.

# terraform/variables.tf

# Defines the AWS region where most resources will be provisioned.
# This impacts the physical location of resources like S3 buckets, Lambda functions (by default), etc.
# It does not affect resources that must be in a specific region (e.g., ACM certs for CloudFront are always in us-east-1).
variable "aws_region" {
  description = "The primary AWS region for deploying resources (e.g., 'eu-west-1', 'us-east-1')."
  type        = string
  default     = "eu-west-1" # Default region set to eu-west-1 (Ireland).
}

# Defines a list of CNAME aliases (alternative domain names) for the CloudFront distribution.
# These are the domain names that viewers will use to access the website.
# Example: ["craicgpt.ie", "www.craicgpt.ie"]
variable "cloudfront_aliases" {
  description = "A list of CNAME aliases (e.g., domain names) for the CloudFront distribution."
  type        = list(string)
  # No default value; this must be provided during deployment.
}

# Specifies the ARN (Amazon Resource Name) of the AWS Secrets Manager secret that stores the LLM API key.
# This variable is sensitive and its value should be handled securely.
variable "llm_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing the LLM API key. This is a sensitive value."
  type        = string
  # No default value; this must be provided during deployment.
  # sensitive = true # Uncomment if using a Terraform version that supports marking variables as sensitive (0.14+).
                   # This prevents the value from being shown in CLI outputs.
}

# Specifies the ARN of the AWS Secrets Manager secret that stores the Image Generator API key.
# This variable is sensitive and its value should be handled securely.
variable "image_gen_api_key_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing the Image Generator API key. This is a sensitive value."
  type        = string
  # No default value; this must be provided during deployment.
  # sensitive = true # Uncomment if using a Terraform version that supports marking variables as sensitive.
}
