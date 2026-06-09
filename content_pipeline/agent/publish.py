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
import re
import time
from typing import Any, Optional

from content_pipeline.content_config import content_cfg

logger = logging.getLogger(__name__)


def s3_key(date_iso: str, prefix: str, name: str = "paper_content.json") -> str:
    """Build the S3 key ``<prefix>/YYYY/MM/DD/<name>``."""
    y, m, d = date_iso.split("-")
    return f"{prefix}/{y}/{m}/{d}/{name}"


def _prefix_for(base: str, language: Optional[str]) -> str:
    """Language-qualify a base prefix: ``content`` → ``de/content`` (None → legacy ``content``).

    Multi-lingual editions live under a per-language prefix (``/<lang>/content/…``);
    a ``None`` language preserves the original single-language layout so existing
    callers/tests are unaffected. English is published explicitly with ``language="en"``.
    """
    return f"{language}/{base}" if language else base


def _content_prefix(language: Optional[str] = None) -> str:
    """The live content prefix, language-qualified when a language is given."""
    return _prefix_for(content_cfg.content_prefix, language)


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


# ── Edition versioning ───────────────────────────────────────────────────────
# Every live publish writes the latest at content/<date>/paper_content.json AND an
# immutable snapshot at content/<date>/versions/<id>.json, then prepends it to
# content/<date>/versions.json (the manifest the site reads to offer prior
# versions). Idempotent on generated_at: re-publishing the SAME edition (the gate
# polls repeatedly) does NOT mint a duplicate version.
def _version_id(generated_at: str) -> str:
    """A URL/key-safe id from an ISO8601 timestamp (2026-06-04T11:50:22… → 20260604T115022)."""
    return re.sub(r"[^0-9A-Za-z]", "", (generated_at or "").split(".")[0]) or "v"


def _hhmm(generated_at: str) -> str:
    """'HH:MM' (UTC) from an ISO8601 timestamp; '' if unparseable."""
    m = re.search(r"T(\d{2}):(\d{2})", generated_at or "")
    return f"{m.group(1)}:{m.group(2)}" if m else ""


def _read_versions_manifest(s3: Any, bucket: str, date_iso: str, language: Optional[str] = None) -> dict:
    """The day's versions.json (for this language), or a fresh empty manifest."""
    key = s3_key(date_iso, _content_prefix(language), "versions.json")
    try:
        data = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        if isinstance(data, dict) and isinstance(data.get("versions"), list):
            return data
    except Exception:  # noqa: BLE001 — no manifest yet / unreadable → start fresh
        pass
    return {"date": date_iso, "versions": []}


def _write_edition_version(s3: Any, bucket: str, date_iso: str, paper: dict,
                           language: Optional[str] = None) -> Optional[str]:
    """Write an immutable snapshot of ``paper`` and prepend it to versions.json.

    Returns the snapshot key, or None if this edition (by generated_at) was already
    versioned — so a repeated publish of the same edition is a no-op. Each language
    keeps its OWN manifest under ``<lang>/content/<date>/versions.json``."""
    gen = str(paper.get("generated_at") or "")
    vid = _version_id(gen)
    manifest = _read_versions_manifest(s3, bucket, date_iso, language)
    versions = manifest["versions"]
    if any(v.get("id") == vid for v in versions):
        return None  # this exact edition is already a version — don't duplicate

    snap_key = s3_key(date_iso, _content_prefix(language), f"versions/{vid}.json")
    s3.put_object(Bucket=bucket, Key=snap_key,
                  Body=json.dumps(paper, ensure_ascii=False, indent=2).encode("utf-8"),
                  ContentType="application/json",
                  CacheControl="public, max-age=31536000, immutable")

    seq = len(versions) + 1
    headliner = ((paper.get("ai") or {}).get("headliner") or {}).get("title", "")
    label = f"v{seq}" + (f" · {_hhmm(gen)}" if _hhmm(gen) else "")
    versions.insert(0, {"id": vid, "generated_at": gen, "seq": seq,
                        "label": label, "headliner": headliner})
    man_key = s3_key(date_iso, _content_prefix(language), "versions.json")
    s3.put_object(Bucket=bucket, Key=man_key,
                  Body=json.dumps({"date": date_iso, "versions": versions},
                                  ensure_ascii=False, indent=2).encode("utf-8"),
                  ContentType="application/json", CacheControl="no-cache")
    logger.info("[publish] version %s (%s) → %s", label, vid, snap_key)
    return snap_key


def publish_paper(
    paper: dict[str, Any],
    date_iso: str,
    *,
    live: bool,
    s3: Any | None = None,
    bucket: Optional[str] = None,
    cloudfront_id: Optional[str] = None,
    site_base_url: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """Upload an edition (and its images) to S3; return the JSON's S3 key.

    Args:
        paper: the schema-v3 paper dict (mutated in place to rewrite image URLs).
        date_iso: edition date.
        live: True → ``content/`` prefix; False → ``preview/`` (draft).
        s3: injected S3 client (defaults to a boto3 client).
        bucket / cloudfront_id / site_base_url: overrides for the configured
            values.
        language: when given, content is stored under a per-language prefix
            ``<lang>/content/…`` (the multi-lingual layout). ``None`` keeps the
            original single-language layout. Each language keeps its own
            ``versions.json``. Translated editions carry absolute (already-uploaded)
            English image URLs, so ``_is_local_path`` skips them → images are SHARED,
            only the per-language audio + JSON upload under ``<lang>/``.
    """
    s3 = s3 or _default_s3()
    bucket = bucket or content_cfg.s3_bucket
    site = site_base_url or content_cfg.site_base_url
    base_prefix = content_cfg.content_prefix if live else content_cfg.preview_prefix
    prefix = _prefix_for(base_prefix, language)

    # 1) Upload any locally-generated images and rewrite their URLs to the CDN.
    #    This MUST cover the AI lead images (headliner + subarticles) as well as
    #    the fun-story images — they are all written as local /tmp paths by the
    #    image step, and any left un-uploaded render as broken images on the site.
    ai = paper.get("ai") or {}
    image_items = [ai.get("headliner"), *(ai.get("subarticles") or []), *(paper.get("fun") or [])]
    for item in image_items:
        if not item:
            continue
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

    # 1b) Upload any locally-generated audio (per-article readings + the daily podcast +
    #     the TL;DR bulletin) and rewrite their URLs to the CDN — same pattern as images.
    #     NB: shorts carry audio (they have no image); the podcast lives at
    #     paper["podcast"] and the headline bulletin at paper["podcast_tldr"]. The
    #     Editor-in-Chief sections (the Editor's Brief and the About page) are narrated
    #     too — include them or their "Listen" button points at an un-uploaded local path.
    audio_items = [paper.get("editors_brief"), ai.get("headliner"),
                   *(ai.get("subarticles") or []), *(ai.get("shorts") or []),
                   *(paper.get("fun") or []), paper.get("about"),
                   paper.get("podcast"), paper.get("podcast_tldr")]
    for item in audio_items:
        if not item:
            continue
        url = item.get("audio_url")
        if not _is_local_path(url):
            continue
        path = url[len("file://"):] if url.startswith("file://") else url
        ctype = "audio/wav" if path.lower().endswith(".wav") else "audio/mpeg"
        aud_key = s3_key(date_iso, prefix, f"audio/{os.path.basename(path)}")
        with open(path, "rb") as fh:
            s3.put_object(Bucket=bucket, Key=aud_key, Body=fh.read(),
                          ContentType=ctype, CacheControl="public, max-age=86400")
        item["audio_url"] = f"{site}/{aud_key}"
        logger.info("[publish] audio → %s", aud_key)

    # 2) Upload the edition JSON.
    key = s3_key(date_iso, prefix)
    body = json.dumps(paper, ensure_ascii=False, indent=2).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body,
                  ContentType="application/json",
                  CacheControl="public, max-age=300")
    logger.info("[publish] edition → s3://%s/%s (live=%s)", bucket, key, live)

    # 2b) Versioning (live only): write an immutable snapshot + update versions.json
    #     so the site can offer prior versions of the day's edition. Idempotent on
    #     generated_at, and never allowed to fail the publish itself.
    manifest_key: Optional[str] = None
    if live:
        try:
            if _write_edition_version(s3, bucket, date_iso, paper, language=language):
                manifest_key = s3_key(date_iso, _content_prefix(language), "versions.json")
        except Exception as exc:  # noqa: BLE001 — versioning must never sink a publish
            logger.warning("[publish] versioning failed: %s", exc)

    # 3) Invalidate CloudFront for the live paths so readers see it immediately.
    cf_id = cloudfront_id or content_cfg.cloudfront_distribution_id
    if live and cf_id:
        _invalidate_cloudfront(cf_id, [key] + ([manifest_key] if manifest_key else []))

    return key


def _invalidate_cloudfront(distribution_id: str, keys) -> None:
    keys = [keys] if isinstance(keys, str) else [k for k in keys if k]
    if not keys:
        return
    try:
        import boto3

        cf = boto3.client("cloudfront", region_name=content_cfg.aws_region)
        items = [f"/{k}" for k in keys]
        cf.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": len(items), "Items": items},
                "CallerReference": str(int(time.time())),
            },
        )
        logger.info("[publish] CloudFront invalidation for %s", ", ".join(items))
    except Exception as exc:  # noqa: BLE001 — invalidation failure shouldn't fail publish
        logger.warning("[publish] CloudFront invalidation failed: %s", exc)
