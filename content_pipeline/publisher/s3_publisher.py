"""
content_pipeline/publisher/s3_publisher.py
============================================
Upload the compiled newspaper JSON to S3 and optionally invalidate CloudFront.

TUTORIAL: boto3 and S3
-----------------------
boto3 is the AWS Python SDK. For S3 uploads you need:
  - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env vars (or an IAM role)
  - The target bucket name and a key (the "path" inside the bucket)

S3 key structure for this project:
    content/YYYY/MM/DD/paper_content.json

The frontend JavaScript fetches:
    https://craicgpt.ie/content/YYYY/MM/DD/paper_content.json

So the key must match exactly what main.js expects.

TUTORIAL: CloudFront Invalidation
-----------------------------------
CloudFront caches content at edge locations around the world. After uploading
new content to S3, we must invalidate the cache so users see today's edition
rather than yesterday's cached version.

Invalidating one path (/content/YYYY/MM/DD/paper_content.json) is cheap
(first 1000 paths/month are free). We also invalidate /index.html just in
case the frontend was updated in the same push.
"""

import json
import logging
from datetime import date

import boto3
from botocore.exceptions import ClientError

from content_pipeline.config import cfg

logger = logging.getLogger(__name__)


def publish_to_s3(paper_content: dict, date_iso: str) -> str:
    """
    Upload paper_content.json to S3 and invalidate the CloudFront cache.

    Args:
        paper_content: The compiled newspaper data dict.
        date_iso:      The date string "YYYY-MM-DD" used to build the S3 key.

    Returns:
        The S3 key where the content was uploaded.

    Raises:
        ClientError: If the S3 upload fails (bucket missing, permissions, etc.)
    """
    # Build the S3 key from the date.
    # e.g. "2026-03-03" → "content/2026/03/03/paper_content.json"
    parts = date_iso.split("-")  # ["2026", "03", "03"]
    s3_key = f"{cfg.aws.s3_content_prefix}/{parts[0]}/{parts[1]}/{parts[2]}/paper_content.json"

    logger.info(f"[publisher] Uploading to s3://{cfg.aws.s3_bucket}/{s3_key}")

    # TUTORIAL: boto3 client vs resource
    # client = low-level, direct API calls, explicit parameters
    # resource = higher-level OO abstraction (deprecated in newer boto3)
    # We use client here — it maps 1:1 to the S3 REST API, easier to debug.
    s3 = boto3.client("s3", region_name=cfg.aws.aws_region)

    json_bytes = json.dumps(paper_content, indent=2, ensure_ascii=False).encode("utf-8")

    try:
        s3.put_object(
            Bucket=cfg.aws.s3_bucket,
            Key=s3_key,
            Body=json_bytes,
            ContentType="application/json",
            # Allow the CloudFront CDN and browsers to cache for 1 hour.
            # CloudFront invalidation (below) resets this immediately on publish.
            CacheControl="public, max-age=3600",
        )
        logger.info(f"[publisher] S3 upload successful: {len(json_bytes)} bytes")
    except ClientError as exc:
        logger.error(f"[publisher] S3 upload failed: {exc}")
        raise

    # Invalidate the CloudFront path so the new content is served immediately.
    _invalidate_cloudfront(s3_key)

    return s3_key


def _invalidate_cloudfront(s3_key: str) -> None:
    """
    Create a CloudFront invalidation for the uploaded content path.
    Silently skips if CLOUDFRONT_DISTRIBUTION_ID is not configured.
    """
    dist_id = cfg.aws.cloudfront_distribution_id
    if not dist_id:
        logger.info("[publisher] No CloudFront distribution ID — skipping invalidation")
        return

    cf = boto3.client("cloudfront", region_name="us-east-1")
    path = f"/{s3_key}"

    logger.info(f"[publisher] Invalidating CloudFront path: {path}")

    try:
        import time
        cf.create_invalidation(
            DistributionId=dist_id,
            InvalidationBatch={
                "Paths": {
                    "Quantity": 1,
                    "Items": [path],
                },
                # Caller reference must be unique per invalidation request.
                "CallerReference": str(int(time.time())),
            },
        )
        logger.info("[publisher] CloudFront invalidation created")
    except ClientError as exc:
        # Log but don't raise — a failed invalidation isn't critical.
        # The content will still be served correctly after the cache TTL expires.
        logger.warning(f"[publisher] CloudFront invalidation failed (non-fatal): {exc}")
