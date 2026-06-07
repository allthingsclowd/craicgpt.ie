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


def _credited_fun():
    # A PR-#26 Irish-creator digest item: it CREDITS a real creator via `source`
    # (the creator's name) and therefore carries NO satire disclaimer — disclaiming
    # "not sourced from the person depicted" would contradict crediting a named one.
    return {
        "title": "Foil Arms and Hog's new sketch", "body": "Body " * 12,
        "source_url": "https://www.youtube.com/watch?v=abc123",
        "source": "Foil Arms and Hog", "kind": "article",
        "image_url": "https://craicgpt.ie/content/2026/06/02/images/f.png",
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


def test_credited_fun_item_valid_without_satire_disclaimer():
    # PR #26 made the fun desk an Irish-creator digest: credited items drop the
    # satire disclaimer. The gate must accept them — a fun item is valid when it is
    # EITHER credited (`source`) OR marked as parody (`satire_disclaimer`). Without
    # this, every live fun edition structurally HOLDs.
    p = good_paper()
    p["fun"] = [_credited_fun() for _ in range(5)]
    res = review.validate_paper(p)
    assert res["valid"] is True, res["reasons"]


def test_uncredited_fun_without_disclaimer_is_invalid():
    # The legal guard stays: a parody item with neither a credit nor a disclaimer
    # is invalid (an AI impression must be marked as one).
    p = good_paper()
    p["fun"][0].pop("source", None)
    p["fun"][0]["satire_disclaimer"] = ""
    res = review.validate_paper(p)
    assert res["valid"] is False
    assert any("parody" in r.lower() or "disclaimer" in r.lower() for r in res["reasons"])


def test_credited_and_voiced_fun_item_is_valid():
    # The live desk: each fun piece CREDITS the real creator (`source`) AND is a
    # celebrity-voice impression (persona byline + `satire_disclaimer` for the
    # voice). Carrying BOTH together is valid — the disclaimer covers the
    # impression, the source credits the creator (they no longer contradict).
    p = good_paper()
    voiced = dict(_credited_fun())
    voiced["persona"] = "Jack Blarney"
    voiced["byline"] = "As told to The Craic Gazette by Jack Blarney"
    voiced["satire_disclaimer"] = "Parody: written by AI in the comic voice of a public figure."
    p["fun"] = [voiced for _ in range(5)]
    res = review.validate_paper(p)
    assert res["valid"] is True, res["reasons"]


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
# compute_consensus is GENERIC over any required agent set. The live DEFAULT is now
# a single rubric judge (see test_consensus_defaults_to_single_rubric below); these
# multi-agent cases pass `required` explicitly to exercise the N-agent mechanism.
TWO = ("openclaw", "hermes")


def test_both_approve_is_approve():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "approve"}}
    c = review.compute_consensus(v, required=TWO)
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
    assert review.compute_consensus(v, required=TWO)["decision"] == "APPROVE"


def test_consensus_defaults_to_single_rubric_verdict():
    # The new default required set is the single in-pipeline rubric judge.
    assert review.DEFAULT_AGENTS == ("rubric",)
    assert review.compute_consensus({"rubric": {"verdict": "APPROVE"}})["decision"] == "APPROVE"
    assert review.compute_consensus({"rubric": {"verdict": "HOLD", "reasons": ["off-brand"]}})["decision"] == "HOLD"
    # A 2-agent set without the rubric verdict no longer approves by default.
    assert review.compute_consensus({"openclaw": {"verdict": "APPROVE"}})["decision"] == "WAIT"


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
    assert review.compute_consensus(verdicts, required=TWO)["decision"] == "HOLD"


def test_verdicts_are_version_keyed_per_apply():
    # Two same-day versions; read_verdicts(vid=...) returns ONLY that version's
    # verdicts, so the gate consenses on the version it's about to publish.
    s3 = FakeS3()
    review.write_verdict("2026-06-04", "openclaw", "APPROVE", ["v1 ok"], vid="V1", s3=s3, bucket="b")
    review.write_verdict("2026-06-04", "hermes", "APPROVE", ["v1 ok"], vid="V1", s3=s3, bucket="b")
    review.write_verdict("2026-06-04", "openclaw", "HOLD", ["v2 off-brand"], vid="V2", s3=s3, bucket="b")
    review.write_verdict("2026-06-04", "hermes", "APPROVE", ["v2 ok"], vid="V2", s3=s3, bucket="b")

    v1 = review.read_verdicts("2026-06-04", vid="V1", s3=s3, bucket="b")
    v2 = review.read_verdicts("2026-06-04", vid="V2", s3=s3, bucket="b")
    assert review.compute_consensus(v1, required=TWO)["decision"] == "APPROVE"   # v1: both approved
    assert review.compute_consensus(v2, required=TWO)["decision"] == "HOLD"      # v2: openclaw held
    assert ("b", "preview/2026/06/04/verdict-openclaw-V1.json") in s3.store
    assert ("b", "preview/2026/06/04/verdict-openclaw-V2.json") in s3.store


def test_read_verdicts_falls_back_to_legacy_per_date():
    # Backward-compat: until the agents write version-keyed verdicts, a gate asking
    # for a vid must still see the legacy per-date verdicts (no vid), so the day's
    # first edition keeps gating + publishing.
    s3 = FakeS3()
    review.write_verdict("2026-06-04", "openclaw", "APPROVE", ["ok"], s3=s3, bucket="b")  # no vid
    review.write_verdict("2026-06-04", "hermes", "APPROVE", ["ok"], s3=s3, bucket="b")    # no vid
    got = review.read_verdicts("2026-06-04", vid="SOMEVID", s3=s3, bucket="b")
    assert set(got) == {"openclaw", "hermes"}                       # legacy verdicts surfaced
    assert review.compute_consensus(got, required=TWO)["decision"] == "APPROVE"


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


def test_review_request_carries_vid_and_stable_per_date_key():
    # With a vid, the request tells the agents WHICH version to review (body `vid`)
    # and points them at ONE stable per-date key — the version is matched by body-vid,
    # not the filename, so a re-review overwrites the same file (IAM-safe, no per-
    # version key). Guards against regressing back to a versioned key template.
    s3 = FakeS3()
    review.write_review_request("2026-06-04", agents=["openclaw", "hermes"],
                                draft_url="https://craicgpt.ie/preview/2026/06/04/paper_content.json",
                                vid="20260604T180000", s3=s3, bucket="b", at="t0")
    rr = review.read_review_request("2026-06-04", s3=s3, bucket="b")
    assert rr["vid"] == "20260604T180000"
    assert rr["verdict_key_template"] == "preview/2026/06/04/verdict-<agent>.json"


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
    g = review.gate("2026-06-02", verdicts=v, status={"state": "complete"},
                    already_live=False, required=TWO)
    assert g["action"] == "publish"


def test_gate_publishes_on_single_rubric_approve():
    # The live default: one in-pipeline rubric APPROVE + complete + host-valid → publish.
    g = review.gate("2026-06-02", verdicts={"rubric": {"verdict": "APPROVE"}},
                    status={"state": "complete"}, already_live=False, valid=True)
    assert g["action"] == "publish"


def test_gate_holds_on_rubric_hold():
    g = review.gate("2026-06-02", verdicts={"rubric": {"verdict": "HOLD", "reasons": ["a dodgy joke"]}},
                    status={"state": "complete"}, already_live=False)
    assert g["action"] == "hold" and "a dodgy joke" in " ".join(g["reasons"])


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
                    already_live=False, valid=False, invalid_reasons=["fun 2 missing image"],
                    required=TWO)
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


# --- HITL passive-approval (the 60-min fail-open, fenced by structural validity) ---
def test_gate_passive_publishes_after_the_window():
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False,
                    valid=True, held_minutes=61, passive_after_minutes=60)
    assert g["action"] == "passive-publish" and g["decision"] == "PASSIVE-APPROVE"


def test_gate_no_passive_before_the_window():
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False,
                    valid=True, held_minutes=10, passive_after_minutes=60)
    assert g["action"] == "hold"


def test_gate_never_passive_publishes_a_structurally_invalid_edition():
    # the safety carve-out: a broken page hard-holds no matter how long it waits
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False,
                    valid=False, invalid_reasons=["headliner missing an image_url"],
                    held_minutes=999, passive_after_minutes=60)
    assert g["action"] == "hold"


def test_gate_passive_disabled_when_no_window_given():
    # default (no window) → classic hold-until-human, never auto-publishes
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False, valid=True)
    assert g["action"] == "hold"


def test_gate_human_hold_directive_pins_and_suppresses_the_timeout():
    g = review.gate("2026-06-03", verdicts=_HOLD2, status=COMPLETE, already_live=False,
                    valid=True, directive={"action": "hold", "by": "graham"},
                    held_minutes=999, passive_after_minutes=60)
    assert g["action"] == "hold"
    assert any("human hold" in r for r in g["reasons"])


def test_write_directive_accepts_hold():
    s3 = FakeS3()
    review.write_directive("2026-06-03", "hold", by="graham", s3=s3, bucket="b", at="t0")
    d = review.read_directive("2026-06-03", s3=s3, bucket="b")
    assert d["action"] == "hold" and d["by"] == "graham"


def test_gate_normal_approve_unaffected_by_no_directive():
    v = {"openclaw": {"verdict": "APPROVE"}, "hermes": {"verdict": "APPROVE"}}
    g = review.gate("2026-06-03", verdicts=v, status=COMPLETE, already_live=False,
                    valid=True, required=TWO)
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
