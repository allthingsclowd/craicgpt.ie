# /terraform/cloudfront.tf

data "aws_caller_identity" "current" {}

resource "aws_cloudfront_origin_access_control" "s3_oac" {
  name                              = "craicgpt-website-assets-oac"
  description                       = "OAC for craicgpt-website-assets S3 bucket"
  origin_access_control_origin_type = "s3"    # Specifies the origin type is S3 [11]
  signing_behavior                  = "always" # CloudFront will always sign requests to the origin [11]
  signing_protocol                  = "sigv4"  # Uses Signature Version 4 for signing [11]
}

# /terraform/cloudfront.tf (continued)

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized" # AWS Managed policy for long TTL static assets [12, 13]
}

resource "aws_cloudfront_cache_policy" "daily_content_cache_policy" {
  name        = "CraicGPT-DailyContent-CachePolicy"
  comment     = "Cache policy for daily content with 24hr TTL"
  default_ttl = 86400 # 24 hours in seconds [14]
  max_ttl     = 86400 # 24 hours
  min_ttl     = 0     # Allows origin to control freshness if headers are set, or caches for default_ttl
  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none" # Can be 'whitelist' if specific headers needed for origin
    }
    query_strings_config {
      query_string_behavior = "none"
    }
    enable_accept_encoding_gzip    = true
    enable_accept_encoding_brotli = true
  }
}

# /terraform/cloudfront.tf (continued)

resource "aws_cloudfront_distribution" "s3_distribution" {
  origin {
    domain_name              = aws_s3_bucket.website_assets.bucket_regional_domain_name # Crucial for OAC [3]
    origin_id                = "S3-craicgpt-website-assets"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3_oac.id # Links OAC to this origin
  }

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CloudFront distribution for craicgpt.ie"
  default_root_object = "index.html"

  aliases = var.cloudfront_aliases # e.g., ["craicgpt.ie", "www.craicgpt.ie"]

  default_cache_behavior {
    allowed_methods        =
    cached_methods         =
    target_origin_id       = "S3-craicgpt-website-assets"
    viewer_protocol_policy = "redirect-to-https" # Enforces HTTPS [3, 15]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id # For static assets (long TTL) [13]
  }

  ordered_cache_behavior {
    path_pattern           = "/content/*"
    allowed_methods        =
    cached_methods         =
    target_origin_id       = "S3-craicgpt-website-assets"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = aws_cloudfront_cache_policy.daily_content_cache_policy.id # For daily content (24hr TTL) [16]
  }

  price_class = "PriceClass_100" # Example: US, Canada, Europe

  restrictions {
    geo_restriction {
      restriction_type = "none" # No geo-restrictions by default
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn # Must be in us-east-1 [17]
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  http_version = "http2"

  tags = {
    Environment = "production"
    Project     = "CraicGPT.ie"
  }

  depends_on = [
    aws_s3_bucket.website_assets
  ]
}

# S3 Bucket Policy allowing CloudFront OAC access
data "aws_iam_policy_document" "s3_website_assets_policy_doc" {
  statement {
    sid    = "AllowCloudFrontOAC"
    effect = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.website_assets.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = ["arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/${aws_cloudfront_distribution.s3_distribution.id}"] # [3]
    }
  }
}

resource "aws_s3_bucket_policy" "website_assets_policy" {
  bucket = aws_s3_bucket.website_assets.id
  policy = data.aws_iam_policy_document.s3_website_assets_policy_doc.json

  depends_on = [aws_cloudfront_distribution.s3_distribution]
}