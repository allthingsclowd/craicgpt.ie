"""Tests for the deep-agent subagent specifications.

The agent does RESEARCH only — three subagents (fun-news researcher, AI-landscape
researcher, link validator); the harness writes the articles. These tests lock
their well-formedness and that each prompt encodes the resolved requirements.
"""

from langchain_core.tools import BaseTool

from content_pipeline.agent import subagents as S


def test_three_research_subagents_with_required_fields_and_unique_names():
    specs = S.SUBAGENTS
    assert len(specs) == 3
    names = {s["name"] for s in specs}
    assert names == {"fun-news-researcher", "ai-landscape-researcher", "link-validator"}
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


def test_no_editor_subagent_the_harness_writes():
    # Editing moved to the harness; the agent must not carry an editor subagent.
    assert "editor" not in {s["name"] for s in S.SUBAGENTS}


def test_editor_in_chief_prompt_is_research_only_with_plan_and_delegation():
    p = S.EDITOR_IN_CHIEF_PROMPT.lower()
    assert "plan" in p
    assert "delegate" in p or "subagent" in p or "task" in p
    assert "research" in p
