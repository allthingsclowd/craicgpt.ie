# Author: Graham Land
# File: terraform/frontend/main.tf
# Purpose: Frontend infrastructure for The Craic Gazette.
#          Provisions S3 (static hosting + content JSON), CloudFront (CDN),
#          ACM (SSL certificate), and Route53 DNS records.
#
# What this does NOT manage:
#   - Content generation (handled by GitHub Actions + LangChain pipeline)
#   - Frontend deployment (handled by .github/workflows/deploy-frontend.yml)
#   - Lambda functions (removed — replaced by self-hosted runner)
#   - EventBridge scheduler (removed — replaced by GitHub Actions cron)

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

# CloudFront SSL certificates must be created in us-east-1 regardless of where
# the rest of the infrastructure lives. This aliased provider enables that.
provider "aws" {
  alias  = "us_east_1_acm"
  region = "us-east-1"
}

data "aws_caller_identity" "current" {}

data "aws_route53_zone" "primary" {
  count = var.enable_cloudfront ? 1 : 0
  name  = var.domain_name
}

# ── ACM: SSL/TLS Certificate ──────────────────────────────────────────────────
module "acm" {
  source = "./modules/acm"
  count  = var.enable_acm ? 1 : 0

  project_name                   = var.project_name
  domain_name                    = var.domain_name
  subject_alternative_names_list = var.cloudfront_aliases
  common_tags                    = local.merged_common_tags

  providers = {
    aws = aws.us_east_1_acm
  }
}

# ── S3: Static Assets + Generated Content JSON ───────────────────────────────
# The bucket holds two things:
#   /index.html, /static_assets/**    ← deployed by deploy-frontend.yml
#   /content/YYYY/MM/DD/paper_content.json ← uploaded by the LangChain pipeline
module "s3" {
  source = "./modules/s3"
  count  = var.enable_s3 ? 1 : 0

  bucket_name       = var.s3_bucket_name_override == "" ? "${var.project_name}-website-assets" : var.s3_bucket_name_override
  common_tags       = local.merged_common_tags
  enable_versioning = var.s3_enable_versioning
  index_document    = var.s3_website_index_document
  error_document    = var.s3_website_error_document
}

# ── CloudFront: CDN Distribution ──────────────────────────────────────────────
module "cloudfront" {
  source = "./modules/cloudfront"
  count  = var.enable_cloudfront ? 1 : 0

  project_name                                  = var.project_name
  s3_bucket_website_assets_id                   = module.s3[0].bucket_id
  s3_bucket_website_assets_arn                  = module.s3[0].bucket_arn
  s3_bucket_website_assets_regional_domain_name = module.s3[0].bucket_regional_domain_name
  acm_certificate_validation_arn                = module.acm[0].certificate_validation_arn
  cloudfront_aliases                            = var.cloudfront_aliases
  common_tags                                   = local.merged_common_tags
  aws_account_id                                = data.aws_caller_identity.current.account_id
  default_root_object                           = var.cloudfront_default_root_object
  price_class                                   = var.cloudfront_price_class
  enable_distribution                           = var.enable_cloudfront
}

# ── Route53: DNS Alias Records for CloudFront ─────────────────────────────────
resource "aws_route53_record" "cloudfront_aliases" {
  count = var.enable_cloudfront ? length(var.cloudfront_aliases) : 0

  zone_id = data.aws_route53_zone.primary[0].zone_id
  name    = var.cloudfront_aliases[count.index]
  type    = "A"

  alias {
    name                   = module.cloudfront[0].distribution_domain_name
    zone_id                = module.cloudfront[0].distribution_hosted_zone_id
    evaluate_target_health = false
  }

  depends_on = [module.cloudfront]
}

# NOTE: Frontend upload is handled by the GitHub Actions deploy-frontend.yml workflow.
# Manual deploy: aws s3 sync frontend/ s3://<bucket-name>/ --delete
