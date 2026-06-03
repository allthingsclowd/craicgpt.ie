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


def test_verdict_of_tolerates_agent_schema_variation():
    # LLM agents vary: 'decision' vs 'verdict', any case.
    assert review.verdict_of({"decision": "approve"}) == "APPROVE"
    assert review.verdict_of({"verdict": "APPROVE"}) == "APPROVE"
    assert review.verdict_of({"vote": "Hold"}) == "HOLD"
    assert review.verdict_of({"agent": "x"}) == ""          # no verdict field
    assert review.verdict_of({"verdict": None}) == ""        # null
    assert review.verdict_of({"verdict": "maybe"}) == ""     # unrecognised


def test_consensus_approves_across_mixed_schemas():
    # The exact shapes openclaw + hermes wrote in the live test.
    v = {"openclaw": {"agent": "openclaw", "decision": "approve"},
         "hermes": {"agent": "hermes", "verdict": "APPROVE"}}
    assert review.compute_consensus(v)["decision"] == "APPROVE"


def test_consensus_does_not_approve_on_unparseable_verdict():
    # Regression: a present-but-unparseable verdict must NOT count as approval.
    v = {"openclaw": {"agent": "openclaw", "foo": "bar"},   # no usable verdict
         "hermes": {"verdict": "APPROVE"}}
    assert review.compute_consensus(v)["decision"] == "WAIT"


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

    def delete_object(self, *, Bucket, Key):
        self.store.pop((Bucket, Key), None)


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


# --- status flag + review-request -------------------------------------------
def test_status_roundtrip():
    s3 = FakeS3()
    assert review.read_status("2026-06-02", s3=s3, bucket="b") is None
    review.write_status("2026-06-02", "generating", s3=s3, bucket="b", at="t0")
    assert review.read_status("2026-06-02", s3=s3, bucket="b")["state"] == "generating"
    review.write_status("2026-06-02", "complete", s3=s3, bucket="b", at="t1",
                        extra={"draft_key": "preview/2026/06/02/paper_content.json"})
    st = review.read_status("2026-06-02", s3=s3, bucket="b")
    assert st["state"] == "complete" and st["draft_key"].endswith("paper_content.json")


def test_review_request_roundtrip():
    s3 = FakeS3()
    review.write_review_request("2026-06-02", agents=["openclaw", "hermes"],
                                draft_url="https://craicgpt.ie/preview/2026/06/02/paper_content.json",
                                s3=s3, bucket="b", at="t0")
    rr = review.read_review_request("2026-06-02", s3=s3, bucket="b")
    assert rr["agents"] == ["openclaw", "hermes"]
    assert "preview" in rr["draft_url"]


# --- gate (the idempotent publisher decision) -------------------------------
def test_gate_retry_when_no_content():
    g = review.gate("2026-06-02", verdicts={}, status=None, already_live=False)
    assert g["action"] == "retry"


def test_gate_retry_when_still_generating():
    g = review.gate("2026-06-02", verdicts={}, status={"state": "generating"}, already_live=False)
    assert g["action"] == "retry"


def test_gate_retry_when_complete_but_awaiting_verdict():
    g = review.gate("2026-06-02", verdicts={"openclaw": {"verdict": "APPROVE"}},
                    status={"state": "complete"}, already_live=False)
    assert g["action"] == "retry" and g["decision"] == "WAIT"


def test_gate_publish_when_complete_and_both_approve():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "APPROVE"}}
    g = review.gate("2026-06-02", verdicts=v, status={"state": "complete"}, already_live=False)
    assert g["action"] == "publish"


def test_gate_hold_when_an_agent_holds():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "HOLD", "reasons": ["off-brand"]}}
    g = review.gate("2026-06-02", verdicts=v, status={"state": "complete"}, already_live=False)
    assert g["action"] == "hold" and "off-brand" in " ".join(g["reasons"])


def test_gate_already_live_short_circuits():
    g = review.gate("2026-06-02", verdicts={}, status=None, already_live=True)
    assert g["action"] == "already-live"


def test_gate_holds_when_agents_approve_but_host_validation_fails():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "APPROVE"}}
    g = review.gate("2026-06-02", verdicts=v, status={"state": "complete"},
                    already_live=False, valid=False, invalid_reasons=["fun 2 missing image"])
    assert g["action"] == "hold"
    assert any("fun 2 missing image" in r for r in g["reasons"])


# --- human directive: write/read/clear --------------------------------------
def test_directive_roundtrip_and_clear():
    s3 = FakeS3()
    assert review.read_directive("2026-06-03", s3=s3, bucket="b") is None
    review.write_directive("2026-06-03", "force-publish", by="graham via openclaw",
                           reason="override", s3=s3, bucket="b", at="t0")
    d = review.read_directive("2026-06-03", s3=s3, bucket="b")
    assert d["action"] == "force-publish" and d["by"] == "graham via openclaw"
    review.clear_directive("2026-06-03", s3=s3, bucket="b")
    assert review.read_directive("2026-06-03", s3=s3, bucket="b") is None


def test_write_directive_rejects_bad_action():
    with pytest.raises(ValueError):
        review.write_directive("2026-06-03", "nuke-it", s3=FakeS3(), bucket="b")


# --- remove_items -----------------------------------------------------------
def test_remove_items_drops_by_title_substring():
    paper = good_paper()
    paper["ai"]["shorts"][1]["title"] = "China's Predictive Police State"
    cleaned, dropped = review.remove_items(paper, ["china's predictive police"])
    assert len(cleaned["ai"]["shorts"]) == 9
    assert dropped == [{"section": "ai.shorts", "title": "China's Predictive Police State"}]
    # deep-copied: the original is untouched
    assert len(paper["ai"]["shorts"]) == 10


def test_remove_items_no_match_is_noop():
    cleaned, dropped = review.remove_items(good_paper(), ["nothing matches this"])
    assert dropped == []
    assert len(cleaned["ai"]["shorts"]) == 10


def test_remove_items_empty_titles_drops_nothing():
    cleaned, dropped = review.remove_items(good_paper(), [])
    assert dropped == [] and len(cleaned["ai"]["shorts"]) == 10


# --- gate honouring a human directive ---------------------------------------
COMPLETE = {"state": "complete"}
_HOLD2 = {"openclaw": {"verdict": "HOLD", "reasons": ["grim"]},
          "hermes": {"verdict": "HOLD", "reasons": ["grim"]}}


def test_gate_force_publish_overrides_hold():
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False,
                    valid=True, directive={"action": "force-publish", "by": "graham"})
    assert g["action"] == "override-publish" and g["decision"] == "OVERRIDE"


def test_gate_force_publish_still_blocked_when_invalid():
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False,
                    valid=False, invalid_reasons=["headliner missing an image_url"],
                    directive={"action": "force-publish"})
    assert g["action"] == "hold"
    assert any("structural" in r for r in g["reasons"])


def test_gate_remove_and_publish_overrides_hold():
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False,
                    directive={"action": "remove-and-publish", "drop": ["china"], "by": "graham"})
    assert g["action"] == "remediate-publish" and g["drop"] == ["china"]


def test_gate_directive_cannot_publish_without_complete_content():
    g = review.gate("2026-06-03", verdicts={}, status=None, already_live=False,
                    directive={"action": "force-publish"})
    assert g["action"] == "retry"


def test_gate_directive_ignored_when_already_live():
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=True,
                    directive={"action": "force-publish"})
    assert g["action"] == "already-live"


def test_gate_normal_approve_unaffected_by_no_directive():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "APPROVE"}}
    g = review.gate("2026-06-03", verdicts=v, status=COMPLETE, already_live=False, valid=True)
    assert g["action"] == "publish"


def test_clear_directive_tombstones_via_put_not_delete():
    # The publish IAM can't DeleteObject, so clear MUST tombstone via PutObject.
    class PutOnlyS3(FakeS3):
        def delete_object(self, **kw):
            raise AssertionError("clear_directive must not call delete_object")

    s3 = PutOnlyS3()
    review.write_directive("2026-06-03", "force-publish", s3=s3, bucket="b", at="t0")
    review.clear_directive("2026-06-03", s3=s3, bucket="b", at="t1")
    raw = json.loads(s3.store[("b", review.directive_key("2026-06-03"))])
    assert raw.get("consumed") is True            # tombstone written
    assert review.read_directive("2026-06-03", s3=s3, bucket="b") is None  # hidden


def test_gate_ignores_a_consumed_directive():
    # A cleared/consumed force-publish must NOT override a HOLD.
    s3 = FakeS3()
    review.write_directive("2026-06-03", "force-publish", s3=s3, bucket="b", at="t0")
    review.clear_directive("2026-06-03", s3=s3, bucket="b", at="t1")
    directive = review.read_directive("2026-06-03", s3=s3, bucket="b")  # → None
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE,
                    already_live=False, valid=True, directive=directive)
    assert g["action"] == "hold"
