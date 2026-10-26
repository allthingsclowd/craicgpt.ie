"""Shared test guards.

The ops-event lane (``notifications.post_ops_event``) POSTs to the LAN Conductor on .75.
No test may reach it: an unstubbed call fails fast with ``ConnectionRefusedError`` instead of
timing out against a real host. A test that wants the lane injects its own fakes
(see ``tests/test_ops_events.py::lane``) — a later ``monkeypatch.setattr`` wins.
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
