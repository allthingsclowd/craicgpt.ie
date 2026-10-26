"""The edition-lifecycle senders move onto the grazlab.ops.event/1 contract.

Fleet #206 item 5 / map #185 decision 4: the site bots stop messaging Graham directly. Each
lifecycle event gets a bucket (from the #187 inventory):

  generated                                   → DROPPED   (no event, no send)
  published                                   → info  / published
  fun_no_comedy, translation_degraded         → warn  / degraded
  qc_flagged                                  → warn  / flagged
  held                                        → page  / decision_needed (+ decision block)

Only `held` may reach Telegram from here, and only on ONE bot, and only when the Conductor
`ops_event` lane did not page it. Offline: Conductor + Telegram are injected fakes, S3 is the
in-memory FakeS3 from test_notifications.
"""

from __future__ import annotations

import json
import re

import pytest

from content_pipeline import notifications
from content_pipeline.agent import cli
from tests.test_notifications import FakeS3

SCHEMA = "grazlab.ops.event/1"
PAGE_KINDS = {"not_published", "service_down", "decision_needed"}


class FakeConductor:
    """Answers POST /workflow with an id and GET /workflow/<id> with a scripted outcome."""

    def __init__(self, *, status="COMPLETED", paged=True, stored=True, fail_post=False):
        self.posted: list[dict] = []
        self.status, self.paged, self.stored, self.fail_post = status, paged, stored, fail_post
        self.suppressed = False
        self.error: str | None = None
        self.task_status = "COMPLETED"  # the ops_event task inside the workflow
        self.get_failures = 0  # transient GET errors before the real answer

    def post(self, url, body, timeout):
        if self.fail_post:
            raise OSError("conductor unreachable")
        self.posted.append(body)
        return "wf-123"

    def get(self, url, timeout):
        if self.get_failures:
            self.get_failures -= 1
            raise OSError("transient")
        out = {"paged": self.paged, "stored": self.stored, "suppressed": self.suppressed}
        if self.error:
            out["error"] = self.error
        return {"status": self.status, "output": out,
                "tasks": [{"taskType": "ops_event", "status": self.task_status}]}


# The fleet's schema.validate rules (grazlab-llm-fleet conductor/ops_events/schema.py), in
# miniature — enough that a malformed craicgpt event fails HERE, not silently on .75.
_TOKEN = re.compile(r"^[a-z0-9_.-]{1,40}$")
_KINDS = PAGE_KINDS | {"workflow_failed", "degraded", "flagged", "published", "cost_threshold",
                       "signup", "review_summary", "heartbeat", "note", "open_incident",
                       "host_metrics"}


def _contract(ev: dict) -> dict:
    assert ev["schema"] == SCHEMA and ev["source"] == "craicgpt"
    assert _TOKEN.match(ev["component"]), ev["component"]
    assert ev["severity"] in {"page", "warn", "info", "debug"} and ev["kind"] in _KINDS
    assert len(ev["title"]) <= 120 and len(ev["detail"]) <= 2000
    assert re.match(r"^\S+$", ev["dedup_key"]) and ev["dedup_key"].startswith("craicgpt:")
    assert ev["ts"].endswith("Z") and isinstance(ev["links"], list)
    assert 1 <= ev["ttl_hours"] <= 720 and ev["unowned"] is False
    if ev["kind"] == "decision_needed":
        d = ev["decision"]
        assert d["nonce"] and d["tier"] in {"SAFE", "EXPLICIT"} and d["options"]
        assert d["expires_at"].endswith("Z")
    return ev


@pytest.fixture
def lane(monkeypatch):
    c = FakeConductor()
    monkeypatch.setattr(notifications, "_http_post_json", c.post)
    monkeypatch.setattr(notifications, "_http_get_json", c.get)
    monkeypatch.setattr(notifications, "_sleep", lambda s: None)
    return c


@pytest.fixture
def telegram(monkeypatch):
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(notifications, "_post",
                        lambda token, chat, text, timeout: sent.append((token, text)) or (True, "ok"))
    return sent


def _cfg(monkeypatch, *, watch="", openclaw="tok-oc", hermes="tok-h"):
    from content_pipeline import content_config
    cc = content_config.content_cfg
    monkeypatch.setattr(cc, "telegram_watch_bot_token", watch)
    monkeypatch.setattr(cc, "telegram_openclaw_bot_token", openclaw)
    monkeypatch.setattr(cc, "telegram_hermes_bot_token", hermes)
    monkeypatch.setattr(cc, "telegram_chat_id", "999")
    monkeypatch.setattr(cc, "telegram_openclaw_chat_id", "")
    monkeypatch.setattr(cc, "telegram_hermes_chat_id", "")


def _event_of(c: FakeConductor) -> dict:
    assert c.posted, "no ops_event workflow was started"
    body = c.posted[-1]
    assert body["name"] == "ops_event" and body["version"] == 1
    return body["input"]["event"]


# ---------------------------------------------------------------- the bucket mapping


def test_generated_is_dropped(lane, telegram) -> None:
    cli._notify_safe("generated", "2026-10-26", vid="V1",
                     draft_url="https://craicgpt.ie/preview/2026/10/26/paper_content.json")
    assert lane.posted == [] and telegram == []
    assert not hasattr(notifications, "notify_generated")


@pytest.mark.parametrize(
    "event, kw, severity, kind",
    [
        ("published", {"live_url": "https://craicgpt.ie/content/2026/10/26/paper_content.json",
                       "approvers": ["rubric"], "link_count": 18, "version": "v1"}, "info", "published"),
        ("fun_no_comedy", {"text": "fun desk shipped without a comedian"}, "warn", "degraded"),
        ("translation_degraded", {"degraded": {"ja": "sections kept English: ai"}}, "warn", "degraded"),
        ("qc_flagged", {"flagged": {"ai.headliner": {"flag": "fabrication", "reason": "no source"}}},
         "warn", "flagged"),
    ],
)
def test_digest_events_post_an_ops_event_and_send_no_telegram(lane, telegram, monkeypatch,
                                                              event, kw, severity, kind) -> None:
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    cli._notify_safe(event, "2026-10-26", vid="V1", **kw)
    ev = _contract(_event_of(lane))
    assert ev["schema"] == SCHEMA and ev["source"] == "craicgpt"
    assert ev["severity"] == severity and ev["kind"] == kind
    assert ev["dedup_key"].startswith(f"craicgpt:{kind}:") and "2026-10-26" in ev["dedup_key"]
    assert "V1" in ev["dedup_key"]
    assert len(ev["title"]) <= 120 and len(ev["detail"]) <= 2000
    assert telegram == [], f"{event} is a digest item — it must not reach Telegram"


def test_translation_degraded_detail_names_each_language(lane, telegram, monkeypatch) -> None:
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    cli._notify_safe("translation_degraded", "2026-07-25", vid="v1",
                     degraded={"ja": "sections kept English: ai", "fr": "only 12% translated (6/51 fields)"})
    ev = _event_of(lane)
    assert "ja" in ev["detail"] and "sections kept English: ai" in ev["detail"]
    assert "fr" in ev["detail"] and "only 12% translated" in ev["detail"]


def test_published_event_carries_the_receipts(lane, telegram, monkeypatch) -> None:
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    cli._notify_safe("published", "2026-10-26", vid="V2",
                     live_url="https://craicgpt.ie/content/2026/10/26/paper_content.json",
                     approvers=["rubric"], link_count=18, version="v2 · 17:30")
    ev = _event_of(lane)
    assert "rubric" in ev["detail"] and "18 source links" in ev["detail"] and "v2 · 17:30" in ev["detail"]
    assert "https://craicgpt.ie/content/2026/10/26/paper_content.json" in ev["links"]


# ---------------------------------------------------------------- held: the one page


def test_held_is_a_decision_needed_page_with_the_passive_window(lane, telegram, monkeypatch) -> None:
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    cli._notify_safe("held", "2026-10-26", vid="V1", reasons=["off-brand short"], passive_minutes=60)
    ev = _contract(_event_of(lane))
    assert ev["severity"] == "page" and ev["kind"] in PAGE_KINDS and ev["kind"] == "decision_needed"
    assert ev["dedup_key"] == "craicgpt:decision_needed:held:2026-10-26:V1"
    d = ev["decision"]
    assert d["tier"] == "SAFE" and set(d["options"]) >= {"override", "hold"}
    assert d["passive_action"] == "publish" and d["nonce"] and d["expires_at"].endswith("Z")
    assert "off-brand short" in ev["detail"]


def test_hard_held_without_a_window_is_explicit(lane, telegram, monkeypatch) -> None:
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    cli._notify_safe("held", "2026-10-26", reasons=["structurally invalid"])
    d = _event_of(lane)["decision"]
    assert d["tier"] == "EXPLICIT" and "passive_action" not in d


def test_held_sends_no_direct_telegram_when_the_lane_paged(lane, telegram, monkeypatch) -> None:
    _cfg(monkeypatch, watch="tok-watch")
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    res = notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=FakeS3())
    assert res["event"]["paged"] is True
    assert telegram == []  # the ops_event task already paged the ONE bot — no double send


def test_held_falls_back_to_one_telegram_when_the_lane_fails(lane, telegram, monkeypatch) -> None:
    _cfg(monkeypatch, watch="tok-watch")
    lane.fail_post = True
    res = notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=FakeS3())
    assert res["event"]["posted"] is False
    assert len(telegram) == 1 and telegram[0][0] == "tok-watch"
    assert "HELD" in telegram[0][1]


def test_held_falls_back_when_the_lane_did_not_page(lane, telegram, monkeypatch) -> None:
    _cfg(monkeypatch, watch="tok-watch")
    lane.status, lane.paged = "FAILED", False  # stored, but DeliveryError on the fleet side
    notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=FakeS3())
    assert len(telegram) == 1


def test_held_sends_no_telegram_while_the_lane_is_still_paging(lane, telegram, monkeypatch) -> None:
    """The wait ran out but the worker HAS the task: it will page — a fallback now is the
    double-send #187 measured."""
    _cfg(monkeypatch, watch="tok-watch")
    lane.status, lane.paged, lane.stored, lane.task_status = "RUNNING", False, False, "IN_PROGRESS"
    s3 = FakeS3()
    notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=s3, bucket="b")
    assert telegram == []
    assert s3.store, "the lane owns it — mark it so the next gate poll does not re-post"


def test_held_falls_back_when_no_worker_picked_the_event_up(lane, telegram, monkeypatch) -> None:
    """Still SCHEDULED at the deadline: the .75 fleet worker is down, nobody will page."""
    _cfg(monkeypatch, watch="tok-watch")
    lane.status, lane.paged, lane.stored, lane.task_status = "RUNNING", False, False, "SCHEDULED"
    notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=FakeS3())
    assert len(telegram) == 1


def test_held_sends_no_telegram_when_the_page_was_suppressed(lane, telegram, monkeypatch) -> None:
    """A hot dedup_key: the fleet already paged this hold within ttl_hours."""
    _cfg(monkeypatch, watch="tok-watch")
    lane.paged, lane.suppressed = False, True
    notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=FakeS3())
    assert telegram == []


def test_held_falls_back_when_the_lane_rejected_the_event(lane, telegram, monkeypatch) -> None:
    _cfg(monkeypatch, watch="tok-watch")
    lane.paged, lane.stored, lane.error = False, False, "EventError: bad component"
    notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=FakeS3())
    assert len(telegram) == 1


def test_a_transient_poll_error_does_not_outlive_a_good_answer(lane, telegram, monkeypatch) -> None:
    lane.get_failures = 1
    s3 = FakeS3()
    res = notifications.notify_held("2026-10-26", ["x"], vid="V1", s3=s3, bucket="b")
    assert res["event"]["paged"] is True and not res["event"].get("error")
    assert s3.store, "a paged hold is marked — the next poll must not page again"
    assert telegram == []


def test_integrity_hold_offers_no_override(lane, telegram, monkeypatch) -> None:
    """EditionHeld in `cli run`: there is no draft, so `cli override` has nothing to publish."""
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    cli._notify_safe("held", "2026-10-26", vid="V1", reasons=["AI desk below floor"], no_draft=True)
    ev = _contract(_event_of(lane))
    assert ev["kind"] == "decision_needed" and "override" not in ev["decision"]["options"]
    assert "override" not in ev["detail"] and "AI desk below floor" in ev["detail"]
    assert ev["dedup_key"] == "craicgpt:decision_needed:held:2026-10-26:V1"


def test_held_link_follows_the_configured_site(lane, telegram, monkeypatch) -> None:
    from content_pipeline import content_config
    monkeypatch.setattr(content_config.content_cfg, "site_base_url", "https://staging.example")
    monkeypatch.setattr(notifications, "_default_s3", lambda: FakeS3())
    cli._notify_safe("held", "2026-10-26", vid="V1", reasons=["x"])
    assert _event_of(lane)["links"] == ["https://staging.example/preview/2026/10/26/paper_content.json"]


def test_digest_event_never_falls_back_to_telegram(lane, telegram, monkeypatch) -> None:
    _cfg(monkeypatch, watch="tok-watch")
    lane.fail_post = True
    res = notifications.notify_published("2026-10-26", "https://x", vid="V1", s3=FakeS3())
    assert res["event"]["posted"] is False and telegram == []


# ---------------------------------------------------------------- once per (date, event, vid)


def test_event_is_posted_once_per_version(lane, telegram, monkeypatch) -> None:
    s3 = FakeS3()
    a = notifications.notify_published("2026-10-26", "https://x", vid="V1", s3=s3, bucket="b")
    b = notifications.notify_published("2026-10-26", "https://x", vid="V1", s3=s3, bucket="b")
    c = notifications.notify_published("2026-10-26", "https://x", vid="V2", s3=s3, bucket="b")
    assert a["event"]["posted"] and b == {"sent": False, "reason": "already-notified", "event": "published"}
    assert c["event"]["posted"] and len(lane.posted) == 2


def test_marker_is_not_set_when_the_lane_failed(lane, telegram, monkeypatch) -> None:
    lane.fail_post = True
    s3 = FakeS3()
    notifications.notify_published("2026-10-26", "https://x", vid="V1", s3=s3, bucket="b")
    assert s3.store == {}  # a transient outage must not permanently suppress the event


# ---------------------------------------------------------------- the single-bot rule


def test_default_target_is_the_watch_bot_when_configured(monkeypatch) -> None:
    _cfg(monkeypatch, watch="tok-watch")
    assert [t[0] for t in notifications._channel_targets()] == ["watch"]
    assert notifications._channel_targets()[0][1] == "tok-watch"


def test_default_target_falls_back_to_exactly_one_agent_bot(monkeypatch) -> None:
    _cfg(monkeypatch, watch="")
    assert len(notifications._channel_targets()) == 1
    _cfg(monkeypatch, watch="", openclaw="")
    assert [t[0] for t in notifications._channel_targets()] == ["hermes"]


def test_both_collapses_to_one_bot(monkeypatch) -> None:
    _cfg(monkeypatch, watch="")
    assert len(notifications._channel_targets("both")) == 1


def test_send_message_default_hits_one_bot_only(monkeypatch, telegram) -> None:
    _cfg(monkeypatch, watch="")
    results = notifications.send_message("hi")
    assert len(results) == 1 and len(telegram) == 1


def test_cli_message_both_is_collapsed(monkeypatch, telegram, capsys) -> None:
    _cfg(monkeypatch, watch="tok-watch")
    import argparse
    rc = cli.cmd_message(argparse.Namespace(text="hi", which="both"))
    assert rc == 0 and len(telegram) == 1 and telegram[0][0] == "tok-watch"
    out = json.loads(capsys.readouterr().out)
    assert out["delivered"] == 1


# ---------------------------------------------------------------- the lane itself


def test_post_ops_event_is_the_sanctioned_conductor_lane(lane) -> None:
    ev = notifications.build_event(severity="info", kind="note", component="t", title="t",
                                   detail="d", dedup_key="craicgpt:note:t")
    res = notifications.post_ops_event(ev)
    assert res["posted"] is True and res["workflow_id"] == "wf-123"
    assert lane.posted[0] == {"name": "ops_event", "version": 1, "input": {"event": ev}}


def test_post_ops_event_fails_soft(lane) -> None:
    lane.fail_post = True
    res = notifications.post_ops_event(notifications.build_event(
        severity="info", kind="note", component="t", title="t", detail="", dedup_key="craicgpt:note:t"))
    assert res["posted"] is False and "unreachable" in res["error"]
