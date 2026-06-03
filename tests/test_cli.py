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
