"""Tests for the autonomous review backbone: validate / verdict / consensus.

These are the deterministic pieces the openclaw + hermes agents run each morning
so "technically valid" is code (testable) and only "harmless" is the LLM's call.
"""

import json

import pytest

from content_pipeline.agent import review


# --- a schema-v3 paper that should pass validation -------------------------
def _art(image=True):
    d = {"title": "A title", "body": "Body text " * 8, "source_url": "https://example.com/a"}
    if image:
        d["image_url"] = "https://craicgpt.ie/content/2026/06/02/images/x.png"
    return d


def _fun():
    return {
        "title": "Fun thing happened", "body": "Body " * 12,
        "source_url": "https://goodnews.example/story", "byline": "Ronald Dump",
        "persona": "Ronald Dump", "kind": "article",
        "image_url": "https://craicgpt.ie/content/2026/06/02/images/f.png",
        "satire_disclaimer": "Parody. Written by AI as a satirical impression.",
    }


def good_paper():
    return {
        "date": "2026-06-02",
        "ai": {
            "headliner": _art(),
            "subarticles": [_art(), _art()],
            "shorts": [{"title": f"Short {i}", "body": "Body " * 8,
                        "source_url": "https://example.com/s"} for i in range(10)],
        },
        "fun": [_fun() for _ in range(5)],
    }


# --- validate_paper ---------------------------------------------------------
def test_good_paper_is_valid():
    res = review.validate_paper(good_paper())
    assert res["valid"] is True, res["reasons"]
    assert res["reasons"] == []


def test_missing_fun_image_is_invalid():
    p = good_paper()
    del p["fun"][2]["image_url"]
    res = review.validate_paper(p)
    assert res["valid"] is False
    assert any("image" in r.lower() for r in res["reasons"])


def test_missing_satire_disclaimer_is_invalid():
    p = good_paper()
    p["fun"][0]["satire_disclaimer"] = ""
    res = review.validate_paper(p)
    assert res["valid"] is False
    assert any("disclaimer" in r.lower() for r in res["reasons"])


def test_too_few_shorts_is_invalid():
    p = good_paper()
    p["ai"]["shorts"] = p["ai"]["shorts"][:3]
    res = review.validate_paper(p)
    assert res["valid"] is False
    assert any("short" in r.lower() for r in res["reasons"])


def test_non_http_source_url_is_invalid():
    p = good_paper()
    p["fun"][1]["source_url"] = "not-a-url"
    res = review.validate_paper(p)
    assert res["valid"] is False
    assert any("source" in r.lower() or "url" in r.lower() for r in res["reasons"])


def test_missing_headliner_is_invalid():
    p = good_paper()
    p["ai"]["headliner"] = {}
    res = review.validate_paper(p)
    assert res["valid"] is False


# --- compute_consensus ------------------------------------------------------
def test_both_approve_is_approve():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "approve"}}
    c = review.compute_consensus(v)
    assert c["decision"] == "APPROVE"


def test_one_hold_is_hold():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "HOLD", "reasons": ["dodgy joke"]}}
    c = review.compute_consensus(v)
    assert c["decision"] == "HOLD"
    assert "dodgy joke" in " ".join(c["reasons"])


def test_missing_second_verdict_waits():
    v = {"openclaw": {"verdict": "APPROVE"}}
    c = review.compute_consensus(v)
    assert c["decision"] == "WAIT"   # no consensus on a single agent's say-so


def test_custom_required_agents():
    v = {"openclaw": {"verdict": "APPROVE"}}
    c = review.compute_consensus(v, required=("openclaw",))
    assert c["decision"] == "APPROVE"


# --- verdict read/write (injected in-memory S3) -----------------------------
class FakeS3:
    def __init__(self):
        self.store = {}

    def put_object(self, *, Bucket, Key, Body, **kw):
        self.store[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.encode()

    def get_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.store:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": _Body(self.store[(Bucket, Key)])}

    def list_objects_v2(self, *, Bucket, Prefix):
        keys = [{"Key": k} for (b, k) in self.store if b == Bucket and k.startswith(Prefix)]
        return {"Contents": keys} if keys else {}


class _Body:
    def __init__(self, b):
        self._b = b

    def read(self):
        return self._b


def test_write_then_read_verdict_roundtrip():
    s3 = FakeS3()
    review.write_verdict("2026-06-02", "openclaw", "APPROVE", ["looks good"],
                         s3=s3, bucket="b", at="2026-06-02T06:15:00Z")
    review.write_verdict("2026-06-02", "hermes", "HOLD", ["off-brand"],
                         s3=s3, bucket="b", at="2026-06-02T06:16:00Z")
    verdicts = review.read_verdicts("2026-06-02", s3=s3, bucket="b")
    assert set(verdicts) == {"openclaw", "hermes"}
    assert verdicts["openclaw"]["verdict"] == "APPROVE"
    assert verdicts["hermes"]["verdict"] == "HOLD"
    # consensus over what was written
    assert review.compute_consensus(verdicts)["decision"] == "HOLD"


def test_read_verdicts_empty_when_none_written():
    assert review.read_verdicts("2026-06-02", s3=FakeS3(), bucket="b") == {}
