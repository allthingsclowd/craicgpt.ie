"""Smoke tests for the agent's @tool wrappers.

These confirm the tools are well-formed LangChain tools (name + description the
LLM reads) and that the offline persona tool returns the expected shape. The
network tools (web_search, fetch_page, generate_image) are only checked for
wiring here; their live behaviour is integration-tested.
"""

import json

from langchain_core.tools import BaseTool

from content_pipeline.agent import tools as T


def _all_tools():
    return [T.web_search, T.fetch_page, T.validate_link, T.assign_journalist_voices,
            T.generate_cover_image]


def test_tools_are_well_formed():
    for tool in _all_tools():
        assert isinstance(tool, BaseTool)
        assert tool.name and tool.name.strip()
        assert tool.description and len(tool.description.strip()) > 10  # LLM reads this


def test_assign_journalist_voices_returns_distinct_personas_with_disclaimer():
    raw = T.assign_journalist_voices.invoke({"count": 3, "seed": "2026-06-02"})
    data = json.loads(raw)
    assert len(data) == 3
    characters = [d["character"] for d in data]
    assert len(set(characters)) == 3
    for d in data:
        assert d["voice_brief"].strip()
        assert d["byline"].startswith("As told to")
        assert "parody" in d["disclaimer"].lower() or "satire" in d["disclaimer"].lower()


def test_assign_journalist_voices_is_day_stable():
    a = T.assign_journalist_voices.invoke({"count": 4, "seed": "2026-06-02"})
    b = T.assign_journalist_voices.invoke({"count": 4, "seed": "2026-06-02"})
    assert a == b
