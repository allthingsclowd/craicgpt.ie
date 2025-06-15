# Author: Graham Land & AI
# Date: YYYY-MM-DD
# Filename and Path: terraform/modules/cloudfront/variables.tf
# Description: Defines input variables for the CloudFront submodule.

variable "project_name" {
  description = "The name of the project."
  type        = string
}

variable "s3_bucket_website_assets_id" {
  description = "ID of the S3 bucket for website assets."
  type        = string
}

variable "s3_bucket_website_assets_arn" {
  description = "ARN of the S3 bucket for website assets."
  type        = string
}

variable "s3_bucket_website_assets_regional_domain_name" {
  description = "Regional domain name of the S3 bucket for website assets."
  type        = string
}

variable "acm_certificate_validation_arn" {
  description = "ARN of the validated ACM certificate for CloudFront."
  type        = string
}

variable "cloudfront_aliases" {
  description = "A list of CNAME aliases for the CloudFront distribution."
  type        = list(string)
  default     = []
}

variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
  default     = {}
}

variable "aws_account_id" {
  description = "The AWS account ID where the CloudFront distribution is deployed. Used for S3 bucket policy."
  type        = string
}

variable "enable_distribution" {
  description = "Set to false to disable the CloudFront distribution."
  type        = bool
  default     = true
}

variable "default_root_object" {
  description = "The default object to serve when the root URL is requested."
  type        = string
  default     = "index.html"
}

variable "price_class" {
  description = "CloudFront price class (e.g., PriceClass_100, PriceClass_200, PriceClass_All)."
  type        = string
  default     = "PriceClass_100"
}
