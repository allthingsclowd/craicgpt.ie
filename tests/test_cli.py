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


def test_run_accepts_no_recency_override():
    # Operator override to force a fresh same-day version when the news pool is thin.
    args = build_parser().parse_args(["run", "--date", "2026-06-02", "--no-recency"])
    assert args.no_recency is True
    # default off — the daily run keeps the recency de-dup
    assert build_parser().parse_args(["run"]).no_recency is False


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


def test_narrate_subcommand_parses_with_defaults():
    a = build_parser().parse_args(["narrate", "--date", "2026-06-06"])
    assert a.command == "narrate"
    assert a.prefix == "preview"
    assert a.publish is False
    assert a.live is False
    assert a.limit is None


def test_narrate_accepts_prefix_limit_publish_live():
    a = build_parser().parse_args(
        ["narrate", "--date", "2026-06-06", "--prefix", "content",
         "--limit", "3", "--publish", "--live"])
    assert a.prefix == "content" and a.limit == 3 and a.publish is True and a.live is True


def test_narrate_requires_date():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["narrate"])


def test_cmd_narrate_enriches_and_reports(monkeypatch, capsys):
    import json as _json

    from content_pipeline.agent import cli

    enriched = {
        "ai": {"headliner": {"title": "H", "audio_url": "u"}, "subarticles": [], "shorts": []},
        "fun": [], "podcast": {"audio_url": "p"}, "edition": {},
    }
    monkeypatch.setattr(
        cli, "_load_edition",
        lambda date, source, prefix="content", language=None: {
            "ai": {"headliner": {"title": "H"}, "subarticles": [], "shorts": []}, "fun": []})
    monkeypatch.setattr("content_pipeline.generate.narration.narrate_paper",
                        lambda paper, **kw: enriched)
    args = build_parser().parse_args(["narrate", "--date", "2026-06-06"])
    rc = cli.cmd_narrate(args)
    assert rc == 0
    report = _json.loads(capsys.readouterr().out)
    assert report["articles_narrated"] == 1
    assert report["podcast"] is True


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


# --- multi-lingual CLI primitives -------------------------------------------
def test_narrate_parses_language():
    a = build_parser().parse_args(["narrate", "--date", "2026-06-08", "--language", "de"])
    assert a.language == "de"
    assert build_parser().parse_args(["narrate", "--date", "2026-06-08"]).language is None


def test_is_translation_only_for_non_source_languages():
    from content_pipeline.agent import cli
    assert cli._is_translation("de") is True
    assert cli._is_translation("en") is False     # the source language stays at the root prefix
    assert cli._is_translation(None) is False


def test_draft_path_is_language_suffixed_for_translations():
    from content_pipeline.agent import cli
    assert cli._draft_path("2026-06-08") == "/tmp/paper_content_2026-06-08.json"
    assert cli._draft_path("2026-06-08", "en") == "/tmp/paper_content_2026-06-08.json"   # source
    assert cli._draft_path("2026-06-08", "de") == "/tmp/paper_content_2026-06-08_de.json"


def test_load_edition_url_is_language_prefixed_for_translations(monkeypatch):
    import httpx

    from content_pipeline.agent import cli

    seen = {}

    class _Resp:
        def json(self):
            return {"ok": True}

    def _get(url, **kw):
        seen["url"] = url
        return _Resp()

    monkeypatch.setattr(httpx, "get", _get)
    cli._load_edition("2026-06-08", None, prefix="content", language="de")
    assert "/de/content/2026/06/08/paper_content.json" in seen["url"]
    cli._load_edition("2026-06-08", None, prefix="content", language="en")   # source → root
    assert seen["url"].endswith("/content/2026/06/08/paper_content.json")
    assert "/en/content/" not in seen["url"]
