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


class _ResearchAgent:
    """Stands in for the research-only agent: returns candidate JSON files."""

    def __init__(self, fun_candidates: list, ai_candidates: list):
        self._files = {
            "/research/fun_candidates.json": {"content": json.dumps(fun_candidates)},
            "/research/ai_candidates.json": {"content": json.dumps(ai_candidates)},
        }

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


def test_run_edition_generates_images_for_leads_and_fun():
    # The harness — not the agent — assigns images. Inject a fake generator so
    # this runs offline; it must image the 3 AI leads + every fun story and
    # overwrite any URL the editor invented.
    ed = _edition()
    ed["fun"][0]["image_url"] = "https://images.unsplash.com/hallucinated"  # editor's bad guess
    calls = []

    def fake_gen(prompt):
        calls.append(prompt)
        return (f"/tmp/img/{len(calls)}.png", "m3/ollama/flux2-klein")

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(ed),
                        image_generate=fake_gen)
    ai = paper["ai"]
    # Headliner + 2 subarticles get a photorealistic image; shorts do not.
    assert ai["headliner"]["image_url"].startswith("/tmp/img/")
    assert ai["headliner"]["_image_model"] == "m3/ollama/flux2-klein"
    for s in ai["subarticles"]:
        assert s["image_url"].startswith("/tmp/img/")
    assert all("image_url" not in s or s.get("image_url") is None for s in ai["shorts"])
    # Every fun story imaged too, overwriting the Unsplash guess.
    for f in paper["fun"]:
        assert f["image_url"].startswith("/tmp/img/")
        assert f["_image_model"] == "m3/ollama/flux2-klein"
    # 1 headliner + 2 subs + 5 fun = 8 images.
    assert len(calls) == 3 + len(paper["fun"])


def test_run_edition_replaces_off_brand_persona():
    from content_pipeline.generate.personas import ROSTER

    ed = _edition()
    ed["fun"][0]["persona"] = "Aquaman"  # not in our parody-journalist roster
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


def test_run_edition_holds_if_no_candidates():
    # No draft AND no research candidates → HOLD (EditionHeld, a RuntimeError
    # subclass), never a thin/empty paper.
    from content_pipeline.agent.editor_in_chief import EditionHeld

    class _Empty:
        def invoke(self, _i, config=None):
            return {"messages": [], "files": {}}

    with pytest.raises(EditionHeld) as exc:
        run_edition("2026-06-02", generated_at="t", agent=_Empty(),
                    ai_feed_fetch=lambda url: None)  # disable harvest → truly no candidates
    assert "candidates" in str(exc.value).lower()


def test_run_edition_writes_from_research_candidates():
    # The real path: agent returns only research candidates; the harness writes
    # the AI section + fun stories via the injected write generator.
    ai_c = [{"title": f"AI cand {i}", "summary": "s", "source_url": f"https://ai/{i}"}
            for i in range(15)]
    fun_c = [{"title": f"Otters rescued {i}", "summary": "lovely", "source_url": f"https://f/{i}",
              "continent": ["Europe", "Asia", "Africa", "Americas", "Oceania"][i % 5]}
             for i in range(12)]

    def fake_write(prompt):
        if "AI editor" in prompt:  # the AI-section call
            return {
                "headliner": {"title": "Big AI Thing", "standfirst": "sf", "body": "b", "source_url": "https://ai/0"},
                "subarticles": [{"title": f"sub{i}", "body": "b", "source_url": "https://ai/1"} for i in range(2)],
                "shorts": [{"title": f"short{i}", "body": "b", "source_url": "https://ai/2"} for i in range(10)],
            }
        return {"title": "Rewritten in voice", "body": "...", "source_url": ""}  # a fun story

    paper = run_edition("2026-06-02", generated_at="t",
                        agent=_ResearchAgent(fun_c, ai_c),
                        write_generate=fake_write,
                        link_fetch=lambda url: 200,  # all candidate links resolve (offline)
                        recent_keys=set(),           # disable the live recency lookup
                        ai_feed_fetch=lambda url: None,  # disable the live feed harvest
                        image_generate=lambda p: ("/tmp/i.png", "flux"))
    assert paper["ai"]["headliner"]["title"] == "Big AI Thing"
    assert len(paper["ai"]["shorts"]) == 10
    assert len(paper["fun"]) == 5
    # Fun stories got a real roster persona + byline + disclaimer + source link.
    from content_pipeline.generate.personas import ROSTER
    for f in paper["fun"]:
        assert f["persona"] in ROSTER
        assert f["byline"].startswith("As told to")
        assert f["satire_disclaimer"]
        assert f["source_url"].startswith("https://f/")


def test_run_edition_grades_with_rubric_when_grade_provided():
    # Goal 3: when a `grade` judge is supplied, run_edition grades the FINISHED
    # edition, attaches the verdict at paper["edition"]["rubric"], and records a
    # `rubric` trace event for the "Under the Hood" drawer. A stub judge keeps it
    # offline (the real judge is an LLM call; tests omit `grade` to skip it).
    seen = {}

    def fake_grade(paper):
        seen["got_fun"] = len(paper.get("fun", []))   # graded the COMPILED paper
        return {"verdict": "APPROVE", "reasons": [], "result": "satisfied",
                "judge_model": "m3/mlx/qwen3.6-35b-a3b-unsloth-8bit"}

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()),
                        grade=fake_grade)
    assert seen["got_fun"] == 5                         # judged after the harness trimmed to 5
    assert paper["edition"]["rubric"]["verdict"] == "APPROVE"
    assert paper["edition"]["rubric"]["judge_model"].endswith("qwen3.6-35b-a3b-unsloth-8bit")
    kinds = [e["kind"] for e in paper["context"]["agent_trace"]]
    assert "rubric" in kinds                            # the drawer will show the judge step


def test_run_edition_records_hold_if_grader_raises():
    # A judge crash must not sink generation — it yields a HOLD verdict the gate surfaces.
    def boom(paper):
        raise RuntimeError("judge unreachable")

    paper = run_edition("2026-06-02", generated_at="t", agent=_FakeAgent(_edition()), grade=boom)
    assert paper["edition"]["rubric"]["verdict"] == "HOLD"
    assert any("judge unreachable" in r for r in paper["edition"]["rubric"]["reasons"])
