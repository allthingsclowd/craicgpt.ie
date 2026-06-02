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


# ── extracting a trace from a real agent run's messages ──────────────────────
class _Msg:
    """Minimal stand-in for a LangChain AIMessage carrying tool_calls."""

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


def test_extract_trace_reads_plan_delegations_and_tools():
    from content_pipeline.agent.trace import extract_trace

    messages = [
        _Msg([{"name": "write_todos", "args": {"todos": [
            {"content": "research fun news", "status": "pending"},
            {"content": "edit", "status": "pending"}]}}]),
        _Msg([{"name": "task", "args": {"subagent_type": "fun-news-researcher",
                                        "description": "find 5 positive stories"}}]),
        _Msg([{"name": "web_search", "args": {"query": "good news Europe"}}]),
        _Msg([]),  # a plain assistant message, no tool calls
    ]
    events = extract_trace(messages)
    kinds = [e["kind"] for e in events]
    assert kinds == ["plan", "subagent", "tool"]
    assert events[0]["detail"]["todos"] == ["research fun news", "edit"]
    assert events[1]["name"] == "fun-news-researcher"
    assert events[2]["name"] == "web_search"


def test_extract_trace_handles_dict_messages_and_is_serialisable():
    import json

    from content_pipeline.agent.trace import extract_trace

    events = extract_trace([{"tool_calls": [{"name": "validate_link",
                                             "args": {"url": "https://x"}}]}])
    assert events[0]["name"] == "validate_link"
    json.dumps(events)
