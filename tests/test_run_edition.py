"""Tests for run_edition — the harness around the deep agent.

The deep agent does the creative work and writes the edition to its virtual
filesystem (result["files"]["/draft/edition.json"]). run_edition extracts that,
enforces the counts deterministically (5 fun, 13 AI) as a safety net, and runs
compile.build_paper to guarantee schema v3 — regardless of how the model
formatted things. The agent is injected here so this runs offline.
"""

import json

from content_pipeline.agent.editor_in_chief import run_edition


class _FakeAgent:
    """Stands in for the compiled deep agent: returns a fixed files dict."""

    def __init__(self, edition: dict):
        self._files = {"/draft/edition.json": {"content": json.dumps(edition)}}

    def invoke(self, _inputs, config=None):
        return {"messages": [], "files": self._files}


def _edition(n_fun=6, n_shorts=12):
    return {
        "ai": {
            "headliner": {"title": "H", "standfirst": "s", "body": "b", "source_url": "https://h"},
            "subarticles": [{"title": "S1", "body": "b", "source_url": "https://s1"},
                            {"title": "S2", "body": "b", "source_url": "https://s2"}],
            "shorts": [{"title": f"sh{i}", "body": "b", "source_url": f"https://x/{i}"}
                       for i in range(n_shorts)],
        },
        "fun": [{"title": f"f{i}", "body": "b", "source_url": f"https://f/{i}",
                 "persona": "Spider-Man", "satire_disclaimer": "Parody.",
                 "image_url": f"https://img/{i}.png", "kind": "article"} for i in range(n_fun)],
    }


def test_run_edition_builds_schema_v3_from_agent_draft():
    paper = run_edition("2026-06-02", generated_at="2026-06-02T06:00:00Z",
                        agent=_FakeAgent(_edition()))
    assert paper["pipeline_version"] == "3.0"
    assert paper["date"] == "2026-06-02"
    assert paper["ai"]["headliner"]["title"] == "H"
    assert "layout" in paper and paper["layout"][0] == "ai.headliner"


def test_run_edition_enforces_counts_as_safety_net():
    # Agent over-produced (6 fun, 12 shorts); harness trims to 5 fun + 10 shorts.
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition(6, 12)))
    assert len(paper["fun"]) == 5
    assert len(paper["ai"]["shorts"]) == 10


def test_run_edition_embeds_agent_trace():
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()))
    assert "agent_trace" in paper["context"]


def test_run_edition_raises_if_no_draft_written():
    class _Empty:
        def invoke(self, _i, config=None):
            return {"messages": [], "files": {}}

    try:
        run_edition("2026-06-02", generated_at="t", agent=_Empty())
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "draft" in str(exc).lower()
