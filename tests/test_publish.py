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


def test_publish_uploads_ai_lead_images_too(tmp_path):
    """Regression: the headliner + subarticle images must be uploaded, not just
    fun images — otherwise the hero images render broken on the live site."""
    head = tmp_path / "head.png"; head.write_bytes(b"\x89PNG head")
    sub0 = tmp_path / "sub0.png"; sub0.write_bytes(b"\x89PNG sub0")
    sub1 = tmp_path / "sub1.png"; sub1.write_bytes(b"\x89PNG sub1")
    fun0 = tmp_path / "fun0.png"; fun0.write_bytes(b"\x89PNG fun0")
    paper = {
        "date": "2026-06-02",
        "ai": {
            "headliner": {"title": "H", "image_url": str(head)},
            "subarticles": [{"title": "S0", "image_url": str(sub0)},
                            {"title": "S1", "image_url": str(sub1)}],
            "shorts": [],
        },
        "fun": [{"title": "f0", "image_url": str(fun0)}],
        "layout": [], "context": {},
    }
    s3 = _FakeS3()
    publish_paper(paper, "2026-06-02", live=True, s3=s3, bucket="b",
                  site_base_url="https://craicgpt.ie")
    img_puts = [p for p in s3.puts if "/images/" in p["Key"]]
    assert len(img_puts) == 4, "all 4 local images (headliner+2 subs+fun) must upload"
    pub = "https://craicgpt.ie/content/2026/06/02/images/"
    assert paper["ai"]["headliner"]["image_url"].startswith(pub)
    assert all(s["image_url"].startswith(pub) for s in paper["ai"]["subarticles"])
    assert paper["fun"][0]["image_url"].startswith(pub)


def test_publish_uploads_local_audio_and_rewrites_url(tmp_path):
    """Per-article readings (incl. shorts) + the podcast audio upload under
    <prefix>/audio/ and get rewritten to public CDN URLs, mirroring images."""
    a_head = tmp_path / "graham-head.mp3"; a_head.write_bytes(b"ID3 head")
    a_short = tmp_path / "graham-short.mp3"; a_short.write_bytes(b"ID3 short")
    a_fun = tmp_path / "graham-fun.mp3"; a_fun.write_bytes(b"ID3 fun")
    a_pod = tmp_path / "podcast.mp3"; a_pod.write_bytes(b"ID3 pod")
    paper = {
        "date": "2026-06-02",
        "ai": {
            "headliner": {"title": "H", "audio_url": str(a_head)},
            "subarticles": [],
            "shorts": [{"title": "S", "audio_url": str(a_short)}],
        },
        "fun": [{"title": "f0", "audio_url": str(a_fun)}],
        "podcast": {"audio_url": str(a_pod), "transcript": "..."},
        "layout": [], "context": {},
    }
    s3 = _FakeS3()
    publish_paper(paper, "2026-06-02", live=True, s3=s3, bucket="b",
                  site_base_url="https://craicgpt.ie")
    aud_puts = [p for p in s3.puts if "/audio/" in p["Key"]]
    assert len(aud_puts) == 4, "headliner + short + fun + podcast audio must upload"
    assert all(p["ContentType"] == "audio/mpeg" for p in aud_puts)
    pub = "https://craicgpt.ie/content/2026/06/02/audio/"
    assert paper["ai"]["headliner"]["audio_url"].startswith(pub)
    assert paper["ai"]["shorts"][0]["audio_url"].startswith(pub)
    assert paper["fun"][0]["audio_url"].startswith(pub)
    assert paper["podcast"]["audio_url"].startswith(pub)


def test_publish_leaves_remote_audio_urls_untouched():
    s3 = _FakeS3()
    paper = {
        "date": "2026-06-02",
        "ai": {"headliner": {"title": "H", "audio_url": "https://cdn/x.mp3"},
               "subarticles": [], "shorts": []},
        "fun": [],
        "podcast": {"audio_url": "https://cdn/p.mp3"},
        "layout": [], "context": {},
    }
    publish_paper(paper, "2026-06-02", live=False, s3=s3, bucket="b")
    assert not [p for p in s3.puts if "/audio/" in p["Key"]]
    assert paper["podcast"]["audio_url"] == "https://cdn/p.mp3"


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


# ── Edition versioning (rev on publish, retain old, always-latest) ────────────
class _StoreS3:
    """Dict-backed fake supporting put_object + get_object (for versioning tests)."""

    def __init__(self):
        self.store = {}
        self.puts = []

    def put_object(self, **kw):
        self.puts.append(kw)
        self.store[kw["Key"]] = kw["Body"]

    def get_object(self, **kw):
        import io
        if kw["Key"] not in self.store:
            raise Exception("NoSuchKey")
        return {"Body": io.BytesIO(self.store[kw["Key"]])}


def _v3(gen, headliner="H"):
    return {"date": "2026-06-04", "generated_at": gen,
            "ai": {"headliner": {"title": headliner}, "subarticles": [], "shorts": []},
            "fun": [], "layout": ["ai.headliner"], "context": {}}


def test_publish_live_writes_immutable_version_and_manifest():
    s3 = _StoreS3()
    publish_paper(_v3("2026-06-04T11:50:22Z"), "2026-06-04", live=True, s3=s3, bucket="b",
                  site_base_url="https://craicgpt.ie")
    keys = [p["Key"] for p in s3.puts]
    assert "content/2026/06/04/paper_content.json" in keys      # latest
    assert "content/2026/06/04/versions.json" in keys           # manifest
    snap = [k for k in keys if k.startswith("content/2026/06/04/versions/") and k != "content/2026/06/04/versions.json"]
    assert snap, "an immutable per-version snapshot must be written"
    man = json.loads(s3.store["content/2026/06/04/versions.json"])
    assert man["date"] == "2026-06-04" and len(man["versions"]) == 1
    assert man["versions"][0]["label"].startswith("v1") and "11:50" in man["versions"][0]["label"]
    assert man["versions"][0]["headliner"] == "H"
    snap_put = next(p for p in s3.puts if p["Key"] == snap[0])
    assert "immutable" in snap_put["CacheControl"]              # snapshots are immutable


def test_publish_idempotent_on_generated_at():
    s3 = _StoreS3()
    for _ in range(2):  # same edition published twice (gate polling)
        publish_paper(_v3("2026-06-04T11:50:22Z"), "2026-06-04", live=True, s3=s3, bucket="b",
                      site_base_url="https://x")
    man = json.loads(s3.store["content/2026/06/04/versions.json"])
    assert len(man["versions"]) == 1  # no duplicate version for the same edition


def test_publish_three_distinct_versions_newest_first():
    s3 = _StoreS3()
    for t in ["2026-06-04T05:00:00Z", "2026-06-04T11:50:00Z", "2026-06-04T15:30:00Z"]:
        publish_paper(_v3(t), "2026-06-04", live=True, s3=s3, bucket="b", site_base_url="https://x")
    man = json.loads(s3.store["content/2026/06/04/versions.json"])
    labels = [v["label"] for v in man["versions"]]
    assert len(man["versions"]) == 3
    assert labels[0].startswith("v3") and "15:30" in labels[0]   # newest first
    assert labels[-1].startswith("v1") and "05:00" in labels[-1]


def test_preview_publish_is_not_versioned():
    s3 = _StoreS3()
    publish_paper(_v3("2026-06-04T11:50:00Z"), "2026-06-04", live=False, s3=s3, bucket="b",
                  site_base_url="https://x")
    assert not any("/versions" in p["Key"] for p in s3.puts)  # preview is transient
