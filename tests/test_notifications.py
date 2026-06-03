"""Tests for the Telegram edition-lifecycle notifier.

The notifier is the single, deterministic source of operator alerts on .75. The
HTTP send is monkeypatched (no network) and S3 is an injected in-memory fake, so
these exercise the fan-out, the configured-or-quiet behaviour, and the
once-per-event idempotency that keeps the 10-min publish-gate poll from spamming.
"""

import json

from content_pipeline import notifications


# --- in-memory S3 (same shape as the app's boto3 client) --------------------
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


class _Body:
    def __init__(self, b):
        self._b = b

    def read(self):
        return self._b


# (label, bot_token, chat_id) — each agent has its own bot, same operator chat.
TARGETS = [("openclaw", "tok-oc", "999"), ("hermes", "tok-h", "999")]


# --- send_message -----------------------------------------------------------
def test_send_message_skips_when_unconfigured():
    # No targets → quiet skip, not an error.
    assert notifications.send_message("hi", targets=[]) == []


def test_send_message_fans_out_via_each_channels_own_bot(monkeypatch):
    posted = []

    def fake_post(token, chat_id, text, timeout):
        posted.append((token, chat_id, text))
        return True, "ok"

    monkeypatch.setattr(notifications, "_post", fake_post)
    results = notifications.send_message("hello", targets=TARGETS)
    assert [r["target"] for r in results] == ["openclaw", "hermes"]
    assert all(r["ok"] for r in results)
    # Each channel posts with ITS OWN token to the shared chat.
    assert [(t, c) for (t, c, _) in posted] == [("tok-oc", "999"), ("tok-h", "999")]


# --- notify_once (idempotency) ----------------------------------------------
def test_notify_once_sends_then_suppresses(monkeypatch):
    sends = []
    monkeypatch.setattr(notifications, "send_message",
                        lambda text, **kw: sends.append(text) or [{"ok": True}])
    s3 = FakeS3()

    first = notifications.notify_once("held", "2026-06-03", "held!", s3=s3, bucket="b")
    assert first["sent"] is True and len(sends) == 1
    # Marker now exists → a second poll is a no-op.
    second = notifications.notify_once("held", "2026-06-03", "held!", s3=s3, bucket="b")
    assert second == {"sent": False, "reason": "already-notified", "event": "held"}
    assert len(sends) == 1  # not sent again

    # Marker is keyed per (date, event): a different event still fires.
    notifications.notify_once("published", "2026-06-03", "live!", s3=s3, bucket="b")
    assert len(sends) == 2


def test_notify_once_does_not_mark_when_send_fails(monkeypatch):
    # A transient outage (no successful send) must NOT permanently suppress.
    monkeypatch.setattr(notifications, "send_message", lambda text, **kw: [{"ok": False}])
    s3 = FakeS3()
    res = notifications.notify_once("generated", "2026-06-03", "x", s3=s3, bucket="b")
    assert res["sent"] is False
    assert (("b", notifications.notified_key("2026-06-03", "generated")) not in s3.store)


# --- lifecycle helpers build the right copy ---------------------------------
def test_lifecycle_helpers_send_expected_text(monkeypatch):
    captured = {}

    def cap(event, date_iso, text, **kw):
        captured[event] = text
        return {"sent": True}

    monkeypatch.setattr(notifications, "notify_once", cap)
    notifications.notify_generated("2026-06-03", "https://craicgpt.ie/preview/x.json")
    notifications.notify_published("2026-06-03", "https://craicgpt.ie/content/x.json")
    notifications.notify_held("2026-06-03", ["off-brand short", "grim item"])

    assert "draft generated" in captured["generated"].lower()
    assert "preview" in captured["generated"]
    assert "published live" in captured["published"].lower()
    assert "HELD" in captured["held"] and "off-brand short" in captured["held"]
