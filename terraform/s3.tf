# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/s3.tf
# Description: Manages the S3 bucket ('craicgpt-website-assets') used for storing all website assets.
#              This includes enabling versioning for data protection, configuring server-side
#              encryption (SSE-S3), setting bucket ownership controls to 'BucketOwnerEnforced'
#              (required for CloudFront OAC), and blocking all public access to the bucket.
#              The bucket policy granting CloudFront access is managed in cloudfront.tf due to dependencies.
#              Prerequisites: None (this file defines the base S3 bucket).
#              Validation: S3 bucket exists in the AWS console with the specified name. Versioning is enabled.
#                          Server-side encryption is set to AES256 by default. Object ownership is
#                          'Bucket owner enforced'. All public access block settings are 'On'.

# terraform/s3.tf

# Defines common values for S3 bucket configuration.
locals {
  bucket_name  = "craicgpt-website-assets" # The globally unique name for the S3 bucket.
  project_name = "CraicGPT.ie"             # Consistent project name for tagging.

  # Common tags to be applied to S3 resources.
  common_tags = {
    Environment = "production"
    Project     = local.project_name
    ManagedBy   = "Terraform"
  }
  # Specific tags for the S3 bucket, merged with common tags.
  bucket_tags = merge(local.common_tags, {
    Name = local.bucket_name
  })
}

# Provisions the primary S3 bucket for storing website assets.
# This bucket will host static content like HTML, CSS, JavaScript, and images,
# as well as dynamically generated content (e.g., daily articles).
resource "aws_s3_bucket" "website_assets" {
  bucket = local.bucket_name # The name of the bucket. Must be globally unique.
  # ACLs (Access Control Lists) are disabled by setting 'BucketOwnerEnforced' for object ownership.
  # This is a security best practice and a prerequisite for using CloudFront OAC (Origin Access Control).
  # Bucket policy will be used to grant access to CloudFront.

  tags = local.bucket_tags
}

# Configures versioning for the website assets S3 bucket.
# Enabling versioning keeps a history of all object versions, protecting against accidental deletions
# or overwrites, and allowing for rollback to previous versions if needed.
resource "aws_s3_bucket_versioning" "website_assets_versioning" {
  bucket = aws_s3_bucket.website_assets.id # References the ID of the 'website_assets' bucket.

  versioning_configuration {
    status = "Enabled" # Enables versioning for the bucket. Can be "Disabled" or "Suspended".
  }
}

# Configures server-side encryption (SSE) for the website assets S3 bucket.
# This ensures that all objects written to the bucket are automatically encrypted at rest.
resource "aws_s3_bucket_server_side_encryption_configuration" "website_assets_sse" {
  bucket = aws_s3_bucket.website_assets.id # References the ID of the 'website_assets' bucket.

  rule {
    apply_server_side_encryption_by_default {
      # Uses SSE-S3 encryption, where S3 manages the encryption keys. [Ref: 1, 2]
      # AES256 is Advanced Encryption Standard with 256-bit keys.
      sse_algorithm = "AES256"
    }
  }
}

# Configures S3 bucket ownership controls.
# 'BucketOwnerEnforced' disables ACLs and ensures the bucket owner owns all objects.
# This is required for using CloudFront Origin Access Control (OAC). [Ref: 3, 4]
resource "aws_s3_bucket_ownership_controls" "website_assets_ownership" {
  bucket = aws_s3_bucket.website_assets.id # References the ID of the 'website_assets' bucket.

  rule {
    # All objects in the bucket are owned by the bucket owner. ACLs are disabled.
    object_ownership = "BucketOwnerEnforced"
  }
}

# Configures the public access block settings for the website assets S3 bucket.
# These settings are crucial for preventing unintended public exposure of bucket contents.
# All public access is blocked, enforcing private access controlled by bucket policies (e.g., for CloudFront OAC).
resource "aws_s3_bucket_public_access_block" "website_assets_pab" {
  bucket = aws_s3_bucket.website_assets.id # References the ID of the 'website_assets' bucket.

  block_public_acls       = true # Blocks new public ACLs and uploading public objects.
  ignore_public_acls      = true # Ignores all public ACLs on this bucket and objects.
  block_public_policy     = true # Blocks new public bucket policies.
  restrict_public_buckets = true # Restricts access to this bucket if it has a public policy.
}

# Note on S3 Bucket Policy:
# The 'aws_s3_bucket_policy' resource for this bucket is defined in 'terraform/cloudfront.tf'.
# This is because the bucket policy needs to grant access to the CloudFront distribution,
# and therefore requires the CloudFront distribution's ARN, creating a dependency.
# Keeping the policy definition close to the CloudFront resource helps manage this dependency.
#
# Example structure (actual resource is in cloudfront.tf):
# data "aws_iam_policy_document" "s3_website_assets_policy_doc" { ... }
# resource "aws_s3_bucket_policy" "website_assets_policy" { ... }