"""Tests for the agent trace recorder.

The recorder captures the deep agent's plan, subagent delegations, and tool
calls into a plain list that goes into paper_content.context.agent_trace — which
the frontend's "Under the Hood" drawer renders as the live LangChain lesson.
"""

from content_pipeline.agent.trace import TraceRecorder


def test_records_plan_subagent_and_tool_events_in_order():
    rec = TraceRecorder()
    rec.plan(["research fun news", "research AI", "edit", "compile"])
    rec.delegate("fun-news-researcher", "find 5 positive stories")
    rec.tool_call("web_search", "query=good news Europe")
    rec.tool_call("validate_link", "https://example.com → 200")

    events = rec.as_list()
    assert [e["kind"] for e in events] == ["plan", "subagent", "tool", "tool"]
    assert events[0]["detail"]["todos"][0] == "research fun news"
    assert events[1]["name"] == "fun-news-researcher"
    assert events[2]["name"] == "web_search"


def test_as_list_is_json_serialisable():
    import json

    rec = TraceRecorder()
    rec.plan(["a"])
    rec.delegate("editor", "write it up")
    json.dumps(rec.as_list())  # must not raise


def test_fallback_event_is_recorded():
    rec = TraceRecorder()
    rec.fallback("brain", local="m3/mlx/qwen3-coder-next-4bit", to="claude-sonnet-4-6",
                 reason="timeout")
    e = rec.as_list()[0]
    assert e["kind"] == "fallback"
    assert e["detail"]["to"] == "claude-sonnet-4-6"
