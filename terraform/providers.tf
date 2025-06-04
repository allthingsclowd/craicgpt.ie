# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/providers.tf
# Description: Configures AWS providers used in the Terraform project. This includes the
#              default AWS provider, which uses a variable for the region, and a specialized
#              AWS provider aliased as 'us_east_1_acm' for resources that must be in 'us-east-1'
#              (specifically, ACM certificates for CloudFront).
#              Prerequisites: AWS credentials (access key, secret key, session token if applicable)
#                             must be configured in the environment or AWS configuration files.
#              Validation: 'terraform init' successfully initializes providers. Resources are
#                          provisioned in the correct AWS regions as specified.

# terraform/providers.tf

# Default AWS Provider Configuration:
# This block configures the default AWS provider for the Terraform project.
# Resources that do not explicitly specify a 'provider' attribute will use this configuration.
# The AWS region is sourced from the 'aws_region' variable, allowing flexibility.
provider "aws" {
  region = var.aws_region # Specifies the AWS region, e.g., "eu-west-1", from variables.tf.
}

# Specialized AWS Provider for ACM in us-east-1:
# This block configures an additional AWS provider instance specifically for the 'us-east-1' region.
# It uses an alias 'us_east_1_acm' to differentiate it from the default provider.
# This specific configuration is MANDATORY for AWS Certificate Manager (ACM) certificates
# that are intended to be used with Amazon CloudFront distributions. CloudFront requires
# ACM certificates to be provisioned in the 'us-east-1' (N. Virginia) region.
provider "aws" {
  alias  = "us_east_1_acm" # Alias to reference this provider instance (e.g., provider = aws.us_east_1_acm).
  region = "us-east-1"     # Sets the region strictly to us-east-1 for ACM certificate provisioning.
}
