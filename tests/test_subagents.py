"""Tests for the deep-agent subagent specifications.

The four subagents (fun-news researcher, AI-landscape researcher, link
validator, editor) are deepagents SubAgent specs. These tests lock their
well-formedness and that each system prompt actually encodes the resolved
requirements — so a prompt edit can't silently drop "non-political", the 13/5
counts, or the satire disclaimer.
"""

from langchain_core.tools import BaseTool

from content_pipeline.agent import subagents as S


def test_four_subagents_with_required_fields_and_unique_names():
    specs = S.SUBAGENTS
    assert len(specs) == 4
    names = [s["name"] for s in specs]
    assert len(set(names)) == 4
    for spec in specs:
        assert spec["name"] and spec["description"] and spec["system_prompt"]
        for t in spec.get("tools", []):
            assert isinstance(t, BaseTool)


def test_fun_news_prompt_encodes_curation_rubric():
    spec = S.by_name("fun-news-researcher")
    p = spec["system_prompt"].lower()
    assert "positive" in p or "fun" in p
    assert "political" in p          # must mention avoiding politics
    assert "5" in spec["system_prompt"]  # five stories
    # It must have the live research tools.
    tool_names = {t.name for t in spec["tools"]}
    assert {"web_search", "validate_link"} <= tool_names


def test_ai_landscape_prompt_encodes_24h_and_counts():
    spec = S.by_name("ai-landscape-researcher")
    p = spec["system_prompt"]
    assert "24" in p                 # last-24h deltas
    assert "13" in p                 # rank 13
    low = p.lower()
    assert "china" in low and "europe" in low  # US/China/EU coverage


def test_editor_prompt_requires_persona_and_disclaimer_tools():
    spec = S.by_name("editor")
    low = spec["system_prompt"].lower()
    assert "marvel" in low or "persona" in low
    assert "disclaimer" in low or "satire" in low or "parody" in low
    tool_names = {t.name for t in spec["tools"]}
    assert "assign_marvel_voices" in tool_names
    # Images are generated deterministically by the harness, not the editor.


def test_editor_in_chief_prompt_mentions_plan_and_delegation():
    p = S.EDITOR_IN_CHIEF_PROMPT.lower()
    assert "plan" in p
    assert "delegate" in p or "subagent" in p or "task" in p
