"""Smoke tests for the CLI parser (no agent run)."""

import pytest

from content_pipeline.agent.cli import build_parser


def test_run_subcommand_parses_with_defaults():
    args = build_parser().parse_args(["run"])
    assert args.command == "run"
    assert args.dry_run is False


def test_run_accepts_date_and_dry_run():
    args = build_parser().parse_args(["run", "--date", "2026-06-02", "--dry-run"])
    assert args.date == "2026-06-02"
    assert args.dry_run is True


def test_run_accepts_publish_draft():
    args = build_parser().parse_args(["run", "--date", "2026-06-02", "--publish-draft"])
    assert args.publish_draft is True


def test_approve_requires_date():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["approve"])  # --date required


def test_publish_requires_date_and_draft():
    args = build_parser().parse_args(["publish", "--date", "2026-06-02", "--draft", "/tmp/d.json"])
    assert args.draft == "/tmp/d.json"


# --- HITL override / remediate / directive ----------------------------------
def test_override_parses_with_publish_and_by():
    a = build_parser().parse_args(
        ["override", "--date", "2026-06-03", "--publish", "--by", "graham via openclaw"])
    assert a.command == "override" and a.publish is True and a.by == "graham via openclaw"


def test_remediate_requires_drop():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["remediate", "--date", "2026-06-03"])  # --drop required


def test_remediate_parses_multiple_drops():
    a = build_parser().parse_args(
        ["remediate", "--date", "2026-06-03", "--drop", "china", "--drop", "war"])
    assert a.drop == ["china", "war"]


def test_directive_parses_clear():
    a = build_parser().parse_args(["directive", "--date", "2026-06-03", "--clear"])
    assert a.command == "directive" and a.clear is True


# --- message subcommand -----------------------------------------------------
def test_message_parses_default_both():
    a = build_parser().parse_args(["message", "--text", "hello"])
    assert a.command == "message" and a.text == "hello" and a.which == "both"


def test_message_to_selects_bot():
    a = build_parser().parse_args(["message", "--text", "x", "--to", "openclaw"])
    assert a.which == "openclaw"


def test_message_requires_text():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["message", "--to", "both"])


# --- content-aware already-live (versioning idempotency) --------------------
def test_already_live_is_content_aware(monkeypatch):
    """The gate republishes when the draft differs from what's live (incl. a stale
    cross-date object), but is a no-op when the live edition IS the current draft."""
    from content_pipeline.agent import cli

    gens = {}
    monkeypatch.setattr(cli, "_edition_generated_at", lambda date, prefix: gens.get(prefix))

    # Stale cross-content live (incident takedown) vs a newer draft → NOT live → republish.
    gens.update(content="2026-06-03T21:46:00Z", preview="2026-06-04T11:50:00Z")
    assert cli._already_live("2026-06-04") is False

    # The current edition is already the latest → already-live → skip (no dup version).
    gens.update(content="2026-06-04T11:50:00Z", preview="2026-06-04T11:50:00Z")
    assert cli._already_live("2026-06-04") is True

    # Nothing live yet → not live.
    gens.update(content=None, preview="2026-06-04T11:50:00Z")
    assert cli._already_live("2026-06-04") is False
