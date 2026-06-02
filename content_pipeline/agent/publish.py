"""
content_pipeline/agent/publish.py
=================================
Publish an edition to S3 — draft to the ``preview/`` prefix (noindex, for human
review) or live to the ``content/`` prefix — uploading any locally-generated
images and rewriting their URLs to the public CDN path, then invalidating
CloudFront.

The S3 client is injected so the logic is unit-testable offline; in production it
defaults to a boto3 client. Draft staging in ``preview/`` IS the durable
approval pause: ``run`` writes the draft there, a human reviews the preview URL,
and ``approve`` re-publishes it under ``content/``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)


def s3_key(date_iso: str, prefix: str, name: str = "paper_content.json") -> str:
    """Build the S3 key ``<prefix>/YYYY/MM/DD/<name>``."""
    y, m, d = date_iso.split("-")
    return f"{prefix}/{y}/{m}/{d}/{name}"


def _default_s3():
    import boto3

    return boto3.client("s3", region_name=content_cfg.aws_region)


def _is_local_path(url: str) -> bool:
    """True if ``url`` is a local file we should upload (not already a web URL)."""
    if not url:
        return False
    if url.startswith("http://") or url.startswith("https://"):
        return False
    path = url[len("file://"):] if url.startswith("file://") else url
    return os.path.exists(path)


def publish_paper(
    paper: dict[str, Any],
    date_iso: str,
    *,
    live: bool,
    s3: Any | None = None,
    bucket: Optional[str] = None,
    cloudfront_id: Optional[str] = None,
    site_base_url: Optional[str] = None,
) -> str:
    """Upload an edition (and its images) to S3; return the JSON's S3 key.

    Args:
        paper: the schema-v3 paper dict (mutated in place to rewrite image URLs).
        date_iso: edition date.
        live: True → ``content/`` prefix; False → ``preview/`` (draft).
        s3: injected S3 client (defaults to a boto3 client).
        bucket / cloudfront_id / site_base_url: overrides for the configured
            values.
    """
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    site = site_base_url or content_cfg.site_base_url
    prefix = content_cfg.content_prefix if live else content_cfg.preview_prefix

    # 1) Upload any locally-generated images and rewrite their URLs to the CDN.
    for item in paper.get("fun", []):
        url = item.get("image_url")
        if not _is_local_path(url):
            continue
        path = url[len("file://"):] if url.startswith("file://") else url
        img_key = s3_key(date_iso, prefix, f"images/{os.path.basename(path)}")
        with open(path, "rb") as fh:
            s3.put_object(Bucket=bucket, Key=img_key, Body=fh.read(),
                          ContentType="image/png",
                          CacheControl="public, max-age=86400")
        item["image_url"] = f"{site}/{img_key}"
        logger.info("[publish] image → %s", img_key)

    # 2) Upload the edition JSON.
    key = s3_key(date_iso, prefix)
    body = json.dumps(paper, ensure_ascii=False, indent=2).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body,
                  ContentType="application/json",
                  CacheControl="public, max-age=300")
    logger.info("[publish] edition → s3://%s/%s (live=%s)", bucket, key, live)

    # 3) Invalidate CloudFront for the live path so readers see it immediately.
    cf_id = cloudfront_id or content_cfg.cloudfront_distribution_id
    if live and cf_id:
        _invalidate_cloudfront(cf_id, key)

    return key


def _invalidate_cloudfront(distribution_id: str, key: str) -> None:
    try:
        import boto3

        cf = boto3.client("cloudfront", region_name=content_cfg.aws_region)
        cf.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": 1, "Items": [f"/{key}"]},
                "CallerReference": str(int(time.time())),
            },
        )
        logger.info("[publish] CloudFront invalidation for /%s", key)
    except Exception as exc:  # noqa: BLE001 — invalidation failure shouldn't fail publish
        logger.warning("[publish] CloudFront invalidation failed: %s", exc)
