# Author: Graham Land
# File: terraform/frontend/variables.tf
# Purpose: Input variables for the CraicGPT frontend infrastructure.
#          Manages only S3 + CloudFront + ACM + Route53.
#          Content generation and frontend deployment are handled by GitHub Actions.

variable "aws_region" {
  description = "The primary AWS region for deploying resources."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Short project name — used for resource naming and tags."
  type        = string
  default     = "craicgpt-frontend"
}

variable "environment" {
  description = "Deployment environment: dev | staging | prod."
  type        = string
  default     = "prod"
}

variable "common_tags" {
  description = "Additional tags to merge onto all taggable resources."
  type        = map(string)
  default     = {}
}

variable "domain_name" {
  description = "Primary domain name for ACM certificate (e.g. 'craicgpt.ie')."
  type        = string
  default     = "craicgpt.ie"
}

variable "cloudfront_aliases" {
  description = "Domain aliases for the CloudFront distribution."
  type        = list(string)
  default     = ["craicgpt.ie"]
}

# ── Module toggles ────────────────────────────────────────────────────────────

variable "enable_acm" {
  description = "Create and validate the ACM SSL certificate."
  type        = bool
  default     = true
}

variable "enable_s3" {
  description = "Create the S3 bucket for static assets and content JSON."
  type        = bool
  default     = true
}

variable "enable_cloudfront" {
  description = "Create the CloudFront CDN distribution."
  type        = bool
  default     = true
}

# ── S3 settings ───────────────────────────────────────────────────────────────

variable "s3_bucket_name_override" {
  description = "Override S3 bucket name (defaults to derived name from project_name)."
  type        = string
  default     = "craicgpt-ie-production"
}

variable "s3_enable_versioning" {
  description = "Enable S3 object versioning."
  type        = bool
  default     = true
}

variable "s3_website_index_document" {
  description = "S3 static website index document."
  type        = string
  default     = "index.html"
}

variable "s3_website_error_document" {
  description = "S3 static website error document."
  type        = string
  default     = "error.html"
}

# ── CloudFront settings ───────────────────────────────────────────────────────

variable "cloudfront_default_root_object" {
  description = "Default object served by CloudFront at the root URL."
  type        = string
  default     = "index.html"
}

variable "cloudfront_price_class" {
  description = "CloudFront price class (PriceClass_100 = US/EU/CA only — cheapest)."
  type        = string
  default     = "PriceClass_100"
}
