"""
content_pipeline/agent/frontend.py
==================================
Deploy the static frontend (index.html, JS, CSS, images) to S3 and invalidate the
CDN — diff-by-ETag so only changed files upload.

This exists because the live site once drifted: the schema-v3 frontend was rebuilt
but never re-synced to S3, so the old shell rendered and the content looked
"missing". The publish gate now runs this on every live publish, so the deployed
site can never silently lag the repo again. Pure boto3 — no `aws` CLI dependency,
unit-testable with an injected S3 client.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import time
from typing import Any, Callable, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)

# Long TTL on hashless assets is fine because we invalidate the exact changed
# paths on deploy; HTML gets a short TTL so a deploy surfaces fast even pre-invalidation.
_HTML_CACHE = "public, max-age=60"
_ASSET_CACHE = "public, max-age=3600"
_EXCLUDE = {"README.md"}


def _default_s3():
    import boto3

    return boto3.client("s3", region_name=content_cfg.aws_region)


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _content_type(path: str) -> str:
    ct, _ = mimetypes.guess_type(path)
    return ct or "application/octet-stream"


def _s3_etag(s3, bucket: str, key: str) -> Optional[str]:
    try:
        return s3.head_object(Bucket=bucket, Key=key)["ETag"].strip('"')
    except Exception:  # noqa: BLE001 — missing object / 404 → needs upload
        return None


def _default_invalidate(distribution_id: str, paths: list[str]) -> None:
    import boto3

    cf = boto3.client("cloudfront", region_name=content_cfg.aws_region)
    cf.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": len(paths), "Items": paths},
            "CallerReference": f"frontend-{int(time.time())}",
        },
    )


def sync_frontend(frontend_dir: str, *, s3: Any | None = None,
                  bucket: Optional[str] = None, cloudfront_id: Optional[str] = None,
                  _invalidate: Optional[Callable[[str, list], None]] = None) -> dict:
    """Upload changed frontend files to S3; invalidate the CDN for what changed.

    Returns ``{"uploaded": [keys]}``. Skips files whose S3 ETag already matches
    (single-part PUT ETag == md5), so re-running is cheap and idempotent.
    """
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    invalidate = _invalidate or _default_invalidate
    uploaded: list[str] = []

    for root, _dirs, files in os.walk(frontend_dir):
        for fn in files:
            local = os.path.join(root, fn)
            key = os.path.relpath(local, frontend_dir).replace(os.sep, "/")
            if key in _EXCLUDE or key.startswith(".") or "/." in key:
                continue
            if _s3_etag(s3, bucket, key) == _md5(local):
                continue  # unchanged
            with open(local, "rb") as fh:
                s3.put_object(
                    Bucket=bucket, Key=key, Body=fh.read(),
                    ContentType=_content_type(local),
                    CacheControl=_HTML_CACHE if key.endswith(".html") else _ASSET_CACHE,
                )
            uploaded.append(key)
            logger.info("[frontend] uploaded %s", key)

    if uploaded:
        cf = cloudfront_id if cloudfront_id is not None else content_cfg.cloudfront_distribution_id
        if cf:
            # Invalidate the changed asset paths + the HTML entry points.
            paths = sorted({f"/{k}" for k in uploaded} | {"/", "/index.html"})
            invalidate(cf, paths)
            logger.info("[frontend] invalidated %d path(s)", len(paths))
    else:
        logger.info("[frontend] nothing to deploy — assets already current")
    return {"uploaded": uploaded}
