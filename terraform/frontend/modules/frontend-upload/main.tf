# Author: Graham Land
# Date: 16th June 2025
# File: terraform/frontend/modules/frontend-upload/main.tf
# Version: 0.0.9
# Purpose: Defines resources for uploading frontend assets to S3 for the frontend-upload submodule.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      # Version constraint inherited from root module
    }
  }
  required_version = ">= 1.8.0" # Ensures Terraform version is new enough
}

# Local Variables
# ---------------
# Defines a map of file extensions to MIME types for setting the Content-Type of uploaded S3 objects.
locals {
  content_types = {
    ".html" : "text/html",
    ".css"  : "text/css",
    ".js"   : "application/javascript",
    ".json" : "application/json",
    ".png"  : "image/png",
    ".jpg"  : "image/jpeg",
    ".jpeg" : "image/jpeg",
    ".gif"  : "image/gif",
    ".svg"  : "image/svg+xml",
    ".ico"  : "image/x-icon",
    ".txt"  : "text/plain",
    ".xml"  : "application/xml",
    # Add more as needed
  }
}

# S3 Object Upload
# ----------------
# This resource block iterates over files found in the specified local directory
# (var.frontend_directory) and uploads them to the target S3 bucket (var.s3_bucket_id).
# The upload process is conditional on var.enable_upload being true and var.frontend_directory being set.
# It sets the Content-Type for each object based on its file extension using the local.content_types map
# and uses the MD5 hash of the file for the ETag to ensure objects are updated only if their content changes.
resource "aws_s3_object" "website_files" {
  # Only process if enable_upload is true and frontend_directory is provided and not empty.
  for_each = var.enable_upload && var.frontend_directory != null && var.frontend_directory != "" ? fileset(var.frontend_directory, "**/*") : toset([])

  bucket = var.s3_bucket_id
  key    = each.value # fileset returns paths relative to the source directory, which is suitable for S3 keys.

  source = "${var.frontend_directory}/${each.value}"
  etag   = filemd5("${var.frontend_directory}/${each.value}") # Used to detect changes in file content

  # Set the content type based on the file extension
  content_type = lookup(local.content_types, regex("\\.[^.]+$", each.value), "binary/octet-stream")
  # ACL is not set as BucketOwnerEnforced is used on the bucket, making objects private by default.
}