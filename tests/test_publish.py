"""Tests for publishing an edition to S3 (draft → preview, live → content).

The S3 client is injected (a fake that records calls), so this runs offline.
Covers: prefix selection, local image upload + URL rewrite, JSON upload, and the
S3 key shape.
"""

import json
import os

from content_pipeline.agent.publish import publish_paper, s3_key


class _FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


def test_s3_key_shape():
    assert s3_key("2026-06-02", "preview") == "preview/2026/06/02/paper_content.json"
    assert s3_key("2026-06-02", "content") == "content/2026/06/02/paper_content.json"


def _paper_with_local_image(tmp_path):
    img = tmp_path / "cover.png"
    img.write_bytes(b"\x89PNG fake bytes")
    return {
        "date": "2026-06-02",
        "ai": {"headliner": {"title": "H"}, "subarticles": [], "shorts": []},
        "fun": [{"title": "f0", "image_url": str(img)}],
        "layout": ["ai.headliner", "fun.0"],
        "context": {},
    }


def test_publish_draft_uploads_json_under_preview(tmp_path):
    s3 = _FakeS3()
    paper = _paper_with_local_image(tmp_path)
    key = publish_paper(paper, "2026-06-02", live=False, s3=s3, bucket="b")
    assert key == "preview/2026/06/02/paper_content.json"
    json_puts = [p for p in s3.puts if p["Key"].endswith("paper_content.json")]
    assert json_puts and json_puts[0]["Bucket"] == "b"
    assert json_puts[0]["ContentType"] == "application/json"


def test_publish_uploads_local_images_and_rewrites_url(tmp_path):
    s3 = _FakeS3()
    paper = _paper_with_local_image(tmp_path)
    publish_paper(paper, "2026-06-02", live=True, s3=s3, bucket="b",
                  site_base_url="https://craicgpt.ie")
    # Image uploaded under content/.../images/ and the story URL rewritten to public.
    img_puts = [p for p in s3.puts if "/images/" in p["Key"]]
    assert img_puts and img_puts[0]["ContentType"] == "image/png"
    assert paper["fun"][0]["image_url"].startswith("https://craicgpt.ie/content/2026/06/02/images/")


def test_publish_live_uses_content_prefix(tmp_path):
    s3 = _FakeS3()
    paper = _paper_with_local_image(tmp_path)
    key = publish_paper(paper, "2026-06-02", live=True, s3=s3, bucket="b")
    assert key.startswith("content/")


def test_publish_leaves_remote_image_urls_untouched():
    s3 = _FakeS3()
    paper = {
        "date": "2026-06-02",
        "ai": {"headliner": {"title": "H"}, "subarticles": [], "shorts": []},
        "fun": [{"title": "f0", "image_url": "https://cdn.example.com/x.png"}],
        "layout": ["ai.headliner", "fun.0"], "context": {},
    }
    publish_paper(paper, "2026-06-02", live=False, s3=s3, bucket="b")
    assert paper["fun"][0]["image_url"] == "https://cdn.example.com/x.png"  # unchanged
