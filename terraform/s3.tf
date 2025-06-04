# /terraform/s3.tf

resource "aws_s3_bucket" "website_assets" {
  bucket = "craicgpt-website-assets"
  # ACLs are not used with BucketOwnerEnforced and OAC
  # See aws_s3_bucket_ownership_controls and aws_s3_bucket_policy
}

resource "aws_s3_bucket_versioning" "website_assets_versioning" {
  bucket = aws_s3_bucket.website_assets.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "website_assets_sse" {
  bucket = aws_s3_bucket.website_assets.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3 encryption [1, 2]
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "website_assets_ownership" {
  bucket = aws_s3_bucket.website_assets.id
  rule {
    object_ownership = "BucketOwnerEnforced" # Required for OAC [3, 4]
  }
}

resource "aws_s3_bucket_public_access_block" "website_assets_pab" {
  bucket = aws_s3_bucket.website_assets.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

# Bucket policy is defined in cloudfront.tf as it depends on the CloudFront distribution ARN
# Example structure provided here for context, actual resource in cloudfront.tf
/*
data "aws_iam_policy_document" "s3_website_assets_policy_doc" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.website_assets.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.s3_distribution.arn] # Placeholder, actual ARN from CloudFront resource
    }
  }
}

resource "aws_s3_bucket_policy" "website_assets_policy" {
  bucket = aws_s3_bucket.website_assets.id
  policy = data.aws_iam_policy_document.s3_website_assets_policy_doc.json
}
*/