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


# --- late-translation catch-up (2026-07-26 incident) --------------------------


def _wire_late(monkeypatch, *, live_langs=(), drafts=None, english_live=True):
    """Stub the S3/publish layer: which languages are live, and which have drafts."""
    drafts = drafts if drafts is not None else {}
    published: list = []

    def fake_edition_paper(date_iso, prefix):
        if prefix == content_cfg.content_prefix:
            return {"date": date_iso} if english_live else None
        lang = prefix.split("/")[0]
        return {"date": date_iso} if lang in live_langs else None

    def fake_load_draft(date_iso, language=None):
        if language not in drafts:
            raise FileNotFoundError(f"no draft for {language}")
        return drafts[language]

    def fake_publish_live(date_iso, paper, *, language=None, note=None):
        published.append(language)
        return 0

    monkeypatch.setattr(cli, "_edition_paper", fake_edition_paper)
    monkeypatch.setattr(cli, "_load_draft", fake_load_draft)
    monkeypatch.setattr(cli, "_publish_paper_live", fake_publish_live)
    return published


def test_late_translation_is_promoted_on_a_later_poll(monkeypatch):
    """The drafts land minutes AFTER the poll that publishes English, so promotion
    must be retried. On 2026-07-26 all five missed the one-shot and Spanish never
    recovered — its narrate timed out, so readers got the previous day's edition."""
    published = _wire_late(
        monkeypatch,
        live_langs=("de",),                       # de already promoted
        drafts={"es": {"date": "2026-07-26"}},    # es draft has since appeared
    )
    out = cli._promote_late_translations("2026-07-26")
    assert published == ["es"]                    # only the missing one
    assert out == {"es": "published"}


def test_already_live_languages_are_not_republished(monkeypatch):
    published = _wire_late(monkeypatch, live_langs=tuple(content_cfg.languages),
                           drafts={"es": {"date": "2026-07-26"}})
    assert cli._promote_late_translations("2026-07-26") == {}
    assert published == []                        # idempotent: cheap no-op every poll


def test_a_draft_from_another_date_is_never_promoted(monkeypatch):
    # Guards against republishing yesterday's draft as today's edition.
    published = _wire_late(monkeypatch, drafts={"es": {"date": "2026-07-25"}})
    assert cli._promote_late_translations("2026-07-26") == {}
    assert published == []


def test_one_failing_language_does_not_stop_the_others(monkeypatch):
    published = _wire_late(
        monkeypatch,
        drafts={"es": {"date": "2026-07-26"}, "fr": {"date": "2026-07-26"}},
    )

    def flaky(date_iso, paper, *, language=None, note=None):
        if language == "es":
            raise RuntimeError("s3 down")
        published.append(language)
        return 0

    monkeypatch.setattr(cli, "_publish_paper_live", flaky)
    out = cli._promote_late_translations("2026-07-26")
    assert "failed" in out["es"] and out["fr"] == "published"
    assert published == ["fr"]


def test_catch_up_never_runs_while_english_is_held(monkeypatch):
    """A translation is a faithful rendering of the English edition and carries the
    SAME verdict — promoting one while English is held would publish content the
    gate has not approved."""
    _wire_late(monkeypatch, english_live=False, drafts={"es": {"date": "2026-06-07"}})
    _wire(monkeypatch, status={"state": "complete"},
          verdicts={"rubric": {"verdict": "HOLD", "reasons": ["dodgy"]}})
    monkeypatch.setattr(review, "gate",
                        lambda date, **kw: {"action": "hold", "decision": "HOLD", "reasons": ["x"]})
    monkeypatch.setattr(cli, "_notify_safe", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_stamp_held_since", lambda d, s: None)
    called = {"n": 0}
    monkeypatch.setattr(cli, "_promote_late_translations",
                        lambda d: called.__setitem__("n", called["n"] + 1) or {})
    cli._run_gate("2026-06-07", ("rubric",), publish=True)
    assert called["n"] == 0            # English not live → no translation promoted
