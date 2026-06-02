"""Tests for run_edition — the harness around the deep agent.

The deep agent does the creative work and writes the edition to its virtual
filesystem (result["files"]["/draft/edition.json"]). run_edition extracts that,
enforces the counts deterministically (5 fun, 13 AI) as a safety net, and runs
compile.build_paper to guarantee schema v3 — regardless of how the model
formatted things. The agent is injected here so this runs offline.
"""

import json

import pytest

from content_pipeline.agent.editor_in_chief import run_edition


@pytest.fixture(autouse=True)
def _no_network_images(monkeypatch):
    """Stub the harness's default FLUX call so run_edition tests stay offline.

    Tests that inject their own image_generate bypass this entirely.
    """
    monkeypatch.setattr(
        "content_pipeline.generate.images.save_image",
        lambda prompt, **kw: ("/tmp/fake-image.png", "test-image-model"),
    )


class _FakeAgent:
    """Stands in for the compiled deep agent: returns a fixed files dict."""

    def __init__(self, edition: dict):
        self._files = {"/draft/edition.json": {"content": json.dumps(edition)}}

    def invoke(self, _inputs, config=None):
        return {"messages": [], "files": self._files}


class _TwoPassAgent:
    """First invoke writes only candidates; the nudge (2nd invoke) writes the draft."""

    def __init__(self, edition: dict):
        self.calls = 0
        self._candidates = {"/research/fun_candidates.json": {"content": "[]"},
                            "/research/ai_candidates.json": {"content": "[]"}}
        self._with_draft = dict(self._candidates)
        self._with_draft["/draft/edition.json"] = {"content": json.dumps(edition)}

    def invoke(self, _inputs, config=None):
        self.calls += 1
        return {"messages": [], "files": self._candidates if self.calls == 1 else self._with_draft}


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


def test_run_edition_finalizes_personas_and_disclaimer():
    from content_pipeline.generate.personas import SATIRE_DISCLAIMER

    ed = _edition()
    ed["fun"][0].pop("persona", None)        # editor left the field blank
    ed["fun"][0]["satire_disclaimer"] = ""   # and the disclaimer blank
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed))
    for f in paper["fun"]:
        assert f["satire_disclaimer"] == SATIRE_DISCLAIMER  # always present (legal)
        assert f.get("persona")                              # assigned where blank
        assert f["byline"].startswith("As told to")


def test_run_edition_generates_fun_images_deterministically():
    # The harness — not the agent — assigns each fun story its image. We inject a
    # fake generator so this runs offline; it must overwrite any URL the editor set.
    ed = _edition()
    ed["fun"][0]["image_url"] = "https://images.unsplash.com/hallucinated"  # editor's bad guess
    calls = []

    def fake_gen(prompt):
        calls.append(prompt)
        return (f"/tmp/img/{len(calls)}.png", "m3/ollama/flux2-klein")

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed),
                        image_generate=fake_gen)
    # Every fun story got a harness-generated local image, not the Unsplash guess.
    for f in paper["fun"]:
        assert f["image_url"].startswith("/tmp/img/")
        assert f["_image_model"] == "m3/ollama/flux2-klein"
    assert len(calls) == len(paper["fun"])  # one image per fun story


def test_run_edition_replaces_off_brand_persona():
    from content_pipeline.generate.personas import ROSTER

    ed = _edition()
    ed["fun"][0]["persona"] = "Aquaman"  # DC, not in our Marvel roster
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed))
    assert paper["fun"][0]["persona"] in ROSTER  # replaced with a roster character


def test_run_edition_stamps_model_attribution():
    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()),
                        text_model="dgx/vllm/qwen3.6-35b-a3b-fp8",
                        image_generate=lambda p: ("/tmp/x.png", "m3/ollama/flux2-klein"))
    assert paper["ai"]["headliner"]["_text_model"] == "dgx/vllm/qwen3.6-35b-a3b-fp8"
    assert paper["fun"][0]["_text_model"] == "dgx/vllm/qwen3.6-35b-a3b-fp8"
    # image model is whatever actually generated the image.
    assert paper["fun"][0]["_image_model"] == "m3/ollama/flux2-klein"


def test_run_edition_raises_if_no_draft_written():
    class _Empty:
        def invoke(self, _i, config=None):
            return {"messages": [], "files": {}}

    try:
        run_edition("2026-06-02", generated_at="t", agent=_Empty())
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "draft" in str(exc).lower()


def test_run_edition_nudges_editor_when_first_pass_skips_draft():
    # Agent gathers candidates but doesn't write the draft on pass 1; the nudge
    # (pass 2) produces it. run_edition must do the second pass and succeed.
    agent = _TwoPassAgent(_edition())
    paper = run_edition("2026-06-02", generated_at="t", agent=agent)
    assert agent.calls == 2
    assert paper["ai"]["headliner"]["title"] == "H"
    assert len(paper["fun"]) == 5
