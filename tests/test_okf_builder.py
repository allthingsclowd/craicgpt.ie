"""OKF (Open Knowledge Format v0.1) builder — deterministic serialization of the
curated research so the rubric judge grounds on it instead of its training data.

Pure, stdlib-only (no PyYAML): same candidates in → byte-identical bundle out.
"""

from __future__ import annotations

from content_pipeline.okf.builder import (
    OKF_VERSION,
    Bundle,
    Concept,
    build_craicgpt_bundle,
    bundle_files,
    bundle_from_json,
    bundle_to_json,
    flatten_for_judge,
    render_concept,
    validate,
)
from content_pipeline.research.curation import Story


def _ai_candidates() -> list:
    return [
        {
            "title": "Fable 5 ships with agentic tool use",
            "summary": "A new 2026 frontier model lands.",
            "source_url": "https://example.com/fable5",
            "why_it_matters": "It changes how agents call tools.",
            "key_points": ["native MCP", "1M context", "cheaper than predecessors"],
            "conclusion": "Worth a look for agent builders.",
        }
    ]


def _fun_picks() -> list:
    return [
        Story(
            title="Sea lion adopts a kayak",
            summary="A heartwarming clip from an Irish creator.",
            source_url="https://youtube.com/watch?v=abc",
            category="animals",
            creator="Foil Arms and Hog",
        )
    ]


def test_render_concept_requires_type() -> None:
    import pytest

    with pytest.raises(ValueError):
        render_concept(Concept(concept_id="ai/x", type="", title="t"))


def test_ai_story_concept_carries_research_body() -> None:
    b = build_craicgpt_bundle(_ai_candidates(), [], date="2026-06-17")
    assert b is not None
    c = b.concepts[0]
    assert c.concept_id.startswith("ai/")
    assert c.type == "AI Story"
    assert c.resource == "https://example.com/fable5"
    # the deterministic research the writer was handed is in the body
    assert "It changes how agents call tools." in c.body
    assert "native MCP" in c.body
    assert "Worth a look" in c.body


def test_fun_story_concept_carries_creator_credit() -> None:
    b = build_craicgpt_bundle([], _fun_picks(), date="2026-06-17")
    assert b is not None
    c = b.concepts[0]
    assert c.type == "Fun Story"
    assert c.resource == "https://youtube.com/watch?v=abc"
    assert "Foil Arms and Hog" in c.tags  # attribution the judge can confirm


def test_build_bundle_has_ai_and_fun_concepts() -> None:
    b = build_craicgpt_bundle(_ai_candidates(), _fun_picks(), date="2026-06-17")
    ids = {c.concept_id for c in b.concepts}
    assert any(i.startswith("ai/") for i in ids)
    assert any(i.startswith("fun/") for i in ids)


def test_empty_research_yields_no_bundle() -> None:
    assert build_craicgpt_bundle([], [], date="2026-06-17") is None


def test_bundle_files_conform_to_okf() -> None:
    files = bundle_files(build_craicgpt_bundle(_ai_candidates(), _fun_picks()))
    assert "index.md" in files
    assert f'okf_version: "{OKF_VERSION}"' in files["index.md"]
    assert validate(files) == []


def test_validate_flags_missing_type() -> None:
    assert any("type" in p for p in validate({"c.md": "---\ntitle: x\n---\nbody"}))


def test_flatten_for_judge_respects_budget() -> None:
    b = build_craicgpt_bundle(_ai_candidates(), _fun_picks())
    assert "Fable 5 ships with agentic tool use" in flatten_for_judge(b, budget=4000)
    assert len(flatten_for_judge(b, budget=150)) <= 150


def test_bundle_json_roundtrip() -> None:
    b = build_craicgpt_bundle(_ai_candidates(), _fun_picks())
    restored = bundle_from_json(bundle_to_json(b))
    assert isinstance(restored, Bundle)
    assert flatten_for_judge(restored, budget=4000) == flatten_for_judge(b, budget=4000)
