"""Offline tests for the gate's HITL passive-approval wiring (cli._run_gate).

The pure decision (review.gate) is covered in test_review.py; here we test the CLI
plumbing: the held-since clock is threaded into the gate, and a first valid judgement
hold stamps the clock. All collaborators are monkeypatched so it runs offline (no S3,
no publish, no Telegram).
"""
from content_pipeline.agent import cli, review
from content_pipeline.content_config import content_cfg


def test_minutes_since_parses_and_handles_garbage():
    assert cli._minutes_since(None) is None
    assert cli._minutes_since("not-a-date") is None
    assert cli._minutes_since("2020-01-01T00:00:00+00:00") > 1_000_000  # years ago


def _wire(monkeypatch, *, status, verdicts):
    monkeypatch.setattr(cli, "_edition_paper", lambda d, p: None)
    monkeypatch.setattr(cli, "_already_live", lambda d: False)
    monkeypatch.setattr(cli, "_host_validate", lambda d: (True, []))
    monkeypatch.setattr(review, "read_status", lambda d, **k: status)
    monkeypatch.setattr(review, "read_verdicts", lambda d, **k: verdicts)
    monkeypatch.setattr(review, "read_directive", lambda d, **k: None)


def test_run_gate_threads_window_and_held_minutes_into_the_gate(monkeypatch):
    _wire(monkeypatch,
          status={"state": "complete", "held_since": "2020-01-01T00:00:00+00:00"},
          verdicts={"rubric": {"verdict": "HOLD", "reasons": ["dodgy"]}})
    captured = {}

    def fake_gate(date, **kw):
        captured.update(kw)
        return {"action": "hold", "decision": "HOLD", "reasons": ["dodgy"]}

    monkeypatch.setattr(review, "gate", fake_gate)
    cli._run_gate("2026-06-07", ("rubric",), publish=False)
    assert captured["passive_after_minutes"] == (content_cfg.hitl_passive_minutes or None)
    assert captured["held_minutes"] > 1_000_000  # parsed from the 2020 held_since


def test_run_gate_stamps_the_clock_on_first_valid_hold(monkeypatch):
    # status has NO held_since yet → the first valid judgement hold starts the clock.
    monkeypatch.setattr(content_cfg, "hitl_passive_minutes", 60)
    _wire(monkeypatch, status={"state": "complete"},
          verdicts={"rubric": {"verdict": "HOLD", "reasons": ["dodgy"]}})
    monkeypatch.setattr(review, "gate",
                        lambda date, **kw: {"action": "hold", "decision": "HOLD", "reasons": ["dodgy"]})
    monkeypatch.setattr(cli, "_notify_safe", lambda *a, **k: None)
    stamped = {}
    monkeypatch.setattr(cli, "_stamp_held_since", lambda d, s: stamped.update(called=True))
    cli._run_gate("2026-06-07", ("rubric",), publish=True)
    assert stamped.get("called") is True
