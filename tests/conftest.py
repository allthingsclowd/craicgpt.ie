"""Shared test guards.

The ops-event lane (``notifications.post_ops_event``) POSTs to the LAN Conductor on .75.
No test may reach it: an unstubbed call fails fast with ``ConnectionRefusedError`` instead of
timing out against a real host. A test that wants the lane injects its own fakes
(see ``tests/test_ops_events.py::lane``) — a later ``monkeypatch.setattr`` wins.

The same goes for the two other real side effects a lifecycle event can reach: Telegram (the
held fallback) and the S3 once-per-event marker. The bot tokens are blanked, so a run on a
host whose env carries them (``.75``) never messages Graham from a test; and the default S3
client refuses, so no marker lands in the real bucket. Tests that want either set them.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_conductor_network(monkeypatch):
    from content_pipeline import notifications

    def _refuse(*a, **k):
        raise ConnectionRefusedError("tests must not reach Conductor — stub the lane")

    monkeypatch.setattr(notifications, "_http_post_json", _refuse)
    monkeypatch.setattr(notifications, "_http_get_json", _refuse)
    monkeypatch.setattr(notifications, "_sleep", lambda s: None)

    def _no_s3():
        raise RuntimeError("tests must not reach S3 — pass s3= or stub _default_s3")

    monkeypatch.setattr(notifications, "_default_s3", _no_s3)
    cc = notifications.content_cfg
    for name in ("telegram_watch_bot_token", "telegram_openclaw_bot_token",
                 "telegram_hermes_bot_token"):
        monkeypatch.setattr(cc, name, "")
