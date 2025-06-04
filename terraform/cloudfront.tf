# Author: Graham Land
# Date: 2025-06-04
# Filename and Path: terraform/cloudfront.tf
# Description: Defines the CloudFront distribution to serve website content from the S3 bucket.
#              Includes Origin Access Control (OAC) for secure S3 access, and cache behaviors
#              for static and dynamic content. Also manages the S3 bucket policy for CloudFront access.
#              Prerequisites: S3 bucket (from s3.tf), ACM certificate ARN (from acm.tf output or direct reference),
#                             CloudFront aliases variable (from variables.tf).
#              Validation: Distribution status 'Deployed' in AWS console. Website accessible via CloudFront domain name
#                          and CNAME aliases over HTTPS. Correct caching headers observed for different content types.
#                          S3 bucket policy correctly references the CloudFront distribution.

# terraform/cloudfront.tf

# Defines common values for CloudFront resources.
locals {
  project_name    = "CraicGPT.ie"                             # Consistent project name for comments and resource names.
  s3_origin_id    = "S3-${aws_s3_bucket.website_assets.id}" # Unique ID for the S3 origin, derived from the S3 bucket ID.
  price_class     = "PriceClass_100"                          # CloudFront price class. PriceClass_100 offers a balance of cost and performance for US, Canada, Europe.
  oac_resource_name = "${aws_s3_bucket.website_assets.id}-oac"  # Name for the OAC resource itself (visible in AWS console).
  oac_description = "Origin Access Control for ${aws_s3_bucket.website_assets.id} S3 bucket" # Description for OAC.

  # Common tags to be applied to all resources in this file, promoting consistency.
  common_tags = {
    Environment = "production"
    Project     = local.project_name
    ManagedBy   = "Terraform"
  }
}

# Retrieves the AWS account ID of the current caller (where Terraform is being executed).
# This account ID is used in the S3 bucket policy to restrict access specifically to
# the CloudFront distribution created within this same AWS account.
data "aws_caller_identity" "current" {}

# Retrieves the AWS managed cache policy named "Managed-CachingOptimized".
# This policy is provided by AWS and is optimized for caching static assets
# by setting long Time-To-Live (TTL) values. [Ref: 12, 13]
data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

# Defines an Origin Access Control (OAC) for the S3 bucket.
# OAC is the recommended method for securely connecting CloudFront to an S3 origin.
# It ensures that content is served only through CloudFront and not directly accessible from the S3 bucket URL.
resource "aws_cloudfront_origin_access_control" "website_assets_oac" {
  name                              = local.oac_resource_name # Name of the OAC in AWS.
  description                       = local.oac_description   # Description for the OAC.
  origin_access_control_origin_type = "s3"     # Specifies the origin type as S3. [Ref: 11]
  signing_behavior                  = "always" # CloudFront will always sign requests to the origin. [Ref: 11]
  signing_protocol                  = "sigv4"  # Uses AWS Signature Version 4 for signing requests. [Ref: 11]
}

# Defines a custom cache policy specifically for content that is expected to update daily,
# such as dynamically generated articles or data. This policy sets a Time-To-Live (TTL) of 24 hours.
resource "aws_cloudfront_cache_policy" "daily_content_cache_policy" {
  name        = "${local.project_name}-DailyContent-CachePolicy" # Unique name for this custom cache policy.
  comment     = "Cache policy for daily content with a 24-hour TTL."
  default_ttl = 86400 # Default TTL in seconds (86400 seconds = 24 hours). [Ref: 14]
  max_ttl     = 86400 # Maximum TTL, also set to 24 hours.
  min_ttl     = 0     # Minimum TTL. If origin provides cache control headers, those can take precedence for shorter cache times.

  # Configuration for parameters included in the cache key and forwarded to the origin.
  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none" # No cookies are included in the cache key or forwarded to the origin.
    }
    headers_config {
      header_behavior = "none" # No headers are included in the cache key or forwarded.
                               # For specific needs, this can be changed to 'whitelist' particular headers.
    }
    query_strings_config {
      query_string_behavior = "none" # No query strings are included in the cache key or forwarded.
    }
    enable_accept_encoding_gzip    = true # Enables CloudFront to request Gzip compressed objects from origin and serve them.
    enable_accept_encoding_brotli = true # Enables CloudFront to request Brotli compressed objects from origin and serve them.
  }
}

# Defines the CloudFront distribution for serving the website content.
# This distribution uses the S3 bucket (via OAC) as its primary origin and includes
# different cache behaviors for static assets and daily generated content.
resource "aws_cloudfront_distribution" "website_distribution" {
  # Origin configuration: specifies the S3 bucket as the source of content.
  origin {
    domain_name              = aws_s3_bucket.website_assets.bucket_regional_domain_name # The regional domain name of the S3 bucket. This is crucial for OAC. [Ref: 3]
    origin_id                = local.s3_origin_id             # A unique identifier for this origin within the distribution.
    origin_access_control_id = aws_cloudfront_origin_access_control.website_assets_oac.id # Links the OAC configuration to this origin.
  }

  enabled             = true               # Enables the distribution, making it active.
  is_ipv6_enabled     = true               # Enables IPv6 support for the distribution.
  comment             = "CloudFront distribution for ${local.project_name}" # A descriptive comment for easier identification in AWS console.
  default_root_object = "index.html"       # Specifies the default object (e.g., "index.html") to serve when the root URL of the distribution is requested.

  aliases = var.cloudfront_aliases # A list of CNAMEs (alternative domain names) for the distribution, e.g., ["craicgpt.ie", "www.craicgpt.ie"].

  # Default cache behavior: applies to requests that don't match any 'ordered_cache_behavior'.
  # Typically used for static assets like HTML, CSS, JS, images.
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"] # HTTP methods allowed for this behavior. OPTIONS is useful for CORS.
    cached_methods         = ["GET", "HEAD"]            # HTTP methods for which CloudFront caches responses.
    target_origin_id       = local.s3_origin_id         # The 'origin_id' of the origin to forward requests to.
    viewer_protocol_policy = "redirect-to-https"      # Redirects all HTTP requests from viewers to HTTPS. [Ref: 3, 15]
    compress               = true                     # Enables CloudFront to automatically compress certain file types.
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id # Uses the AWS managed 'CachingOptimized' policy. [Ref: 13]
  }

  # Ordered cache behavior for daily generated content.
  # This behavior applies to requests matching the "/content/*" path pattern, using a shorter TTL.
  ordered_cache_behavior {
    path_pattern           = "/content/*"               # The path pattern that triggers this behavior (e.g., for articles).
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = aws_cloudfront_cache_policy.daily_content_cache_policy.id # Uses the custom 'daily_content_cache_policy'. [Ref: 16]
  }

  price_class = local.price_class # Sets the price class for the distribution, affecting cost and geographic reach.

  # Restrictions configuration: can be used to apply geographic restrictions (geo-blocking).
  restrictions {
    geo_restriction {
      restriction_type = "none" # 'none' means no geographic restrictions are applied. Others: 'whitelist', 'blacklist'.
    }
  }

  # Viewer certificate configuration: specifies the SSL/TLS certificate for enabling HTTPS.
  viewer_certificate {
    # Directly references the validated ACM certificate resource from 'acm.tf'.
    # This ensures that CloudFront uses a valid, AWS-issued certificate for the specified domain(s).
    acm_certificate_arn      = aws_acm_certificate_validation.site_certificate_validation.certificate_arn # ARN of the ACM certificate in us-east-1. [Ref: 17]
    ssl_support_method       = "sni-only"             # Specifies Server Name Indication (SNI), allowing multiple domains with one IP.
    minimum_protocol_version = "TLSv1.2_2021"         # Sets the minimum TLS protocol version for viewer connections.
  }

  http_version = "http2" # Enables HTTP/2 for improved performance in viewer connections.

  tags = local.common_tags # Applies the defined common tags to the CloudFront distribution.

  # Explicit dependency on the S3 bucket.
  # This ensures that the S3 bucket is fully created before CloudFront attempts to configure it as an origin.
  depends_on = [
    aws_s3_bucket.website_assets
  ]
}

# Defines the IAM policy document that grants the CloudFront distribution permission to access objects in the S3 bucket.
# This policy is then applied to the S3 bucket using the 'aws_s3_bucket_policy' resource.
data "aws_iam_policy_document" "s3_website_assets_policy_doc" {
  statement {
    sid    = "AllowCloudFrontOAC" # A descriptive statement ID.
    effect = "Allow"              # Specifies that this statement allows access.
    actions   = ["s3:GetObject"]  # Allows CloudFront to perform 's3:GetObject' actions, i.e., read objects.
    resources = ["${aws_s3_bucket.website_assets.arn}/*"] # Grants permission to all objects ("/*") within the specified S3 bucket.

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"] # Restricts the principal to the CloudFront AWS service.
    }

    # Condition to ensure that requests originate only from the specific CloudFront distribution created by this Terraform configuration.
    # This prevents other CloudFront distributions or AWS services from accessing the bucket, even if they belong to the same account.
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn" # Condition key that checks the ARN of the source making the request.
      values   = ["arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/${aws_cloudfront_distribution.website_distribution.id}"] # The ARN of this CloudFront distribution. [Ref: 3]
    }
  }
}

# Applies the S3 bucket policy (defined above) to the website assets S3 bucket.
# This policy is crucial for allowing the CloudFront distribution (via OAC) to securely fetch objects from the bucket.
resource "aws_s3_bucket_policy" "website_assets_policy" {
  bucket = aws_s3_bucket.website_assets.id # Associates this policy with the website_assets S3 bucket.
  policy = data.aws_iam_policy_document.s3_website_assets_policy_doc.json # The IAM policy document in JSON format.

  # Explicit dependency on the CloudFront distribution.
  # This ensures that the CloudFront distribution exists and its ID is available before this bucket policy,
  # which references the distribution's ARN, is applied.
  depends_on = [aws_cloudfront_distribution.website_distribution]
}